from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from .admin_auth import AdminPrincipal
from .database import Database
from .errors import ApiError


SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MICROS = Decimal(1_000_000)
TOKEN_UNIT = 1_000_000
VIDEO_RESOLUTIONS = ("480p", "720p", "768p", "1080p")


def current_month(now: datetime | None = None) -> str:
    local = (now or datetime.now(timezone.utc)).astimezone(SHANGHAI)
    return f"{local.year:04d}-{local.month:02d}"


def next_month(month: str) -> str:
    year, value = (int(part) for part in month.split("-"))
    return f"{year + (value == 12):04d}-{1 if value == 12 else value + 1:02d}"


def previous_month(month: str) -> str:
    year, value = (int(part) for part in month.split("-"))
    return f"{year - (value == 1):04d}-{12 if value == 1 else value - 1:02d}"


def validate_month(value: str) -> str:
    if not MONTH_PATTERN.fullmatch(value):
        raise ApiError("账期必须使用YYYY-MM格式", 422, "billing_month_invalid")
    return value


def month_bounds_utc(month: str) -> tuple[str, str]:
    validate_month(month)
    start = datetime.strptime(month + "-01", "%Y-%m-%d").replace(tzinfo=SHANGHAI)
    end_month = next_month(month)
    end = datetime.strptime(end_month + "-01", "%Y-%m-%d").replace(tzinfo=SHANGHAI)
    return (
        start.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        end.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )


def timestamp_month(value: str | int | float | None) -> str:
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000
        parsed = datetime.fromtimestamp(numeric, timezone.utc)
    else:
        raw = str(value or "").strip()
        if not raw:
            parsed = datetime.now(timezone.utc)
        else:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
    local = parsed.astimezone(SHANGHAI)
    return f"{local.year:04d}-{local.month:02d}"


def normalize_resolution(value: Any, width: Any = None, height: Any = None) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in VIDEO_RESOLUTIONS:
        return raw
    if raw.endswith("p") and raw[:-1].isdigit():
        return raw
    try:
        dimensions = [item for item in (int(width or 0), int(height or 0)) if item > 0]
    except (TypeError, ValueError):
        dimensions = []
    if dimensions:
        # Resolution labels refer to the short edge for both landscape and
        # portrait videos (1280x720 and 720x1280 are both 720p).
        short_edge = min(dimensions)
        return min(VIDEO_RESOLUTIONS, key=lambda item: abs(int(item[:-1]) - short_edge))
    return None


def yuan_to_micros(value: str) -> int:
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ApiError("金额格式无效", 422, "billing_amount_invalid") from error
    if not amount.is_finite() or amount < 0 or amount > Decimal("100000000"):
        raise ApiError("金额必须在0到1亿元之间", 422, "billing_amount_invalid")
    return int((amount * MICROS).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def signed_yuan_to_micros(value: str) -> int:
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ApiError("调整金额格式无效", 422, "billing_adjustment_invalid") from error
    if not amount.is_finite() or amount == 0 or abs(amount) > Decimal("100000000"):
        raise ApiError("调整金额必须为非零且不超过1亿元", 422, "billing_adjustment_invalid")
    return int((amount * MICROS).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def micros_to_yuan(value: int | None) -> str:
    return f"{(Decimal(int(value or 0)) / MICROS):.6f}"


def _loaded(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(value) if isinstance(value, str) else fallback
    except json.JSONDecodeError:
        return fallback


class BillingManager:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._lock = asyncio.Lock()

    async def maintenance_loop(self) -> None:
        while True:
            try:
                await self.reconcile()
            except Exception:
                # Billing is deliberately outside the customer request path. A later
                # pass or explicit recalculation retries incomplete work.
                pass
            await asyncio.sleep(60)

    @staticmethod
    def _principal_actor(principal: AdminPrincipal) -> str:
        return principal.id

    def _project_exists(self, project_name: str) -> None:
        if not self.database.project_exists(project_name):
            raise ApiError("项目不存在", 404, "project_not_found")

    def _catalog_model(self, alias: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT alias,display_name,provider,modality,upstream_model,capabilities_json "
                "FROM model_catalog WHERE alias=? AND enabled=1",
                (alias,),
            ).fetchone()
        if row is None:
            raise ApiError("模型不存在或已下架", 404, "billing_model_not_found")
        result = dict(row)
        result["capabilities"] = _loaded(result.pop("capabilities_json"), {})
        return result

    @staticmethod
    def _rate_rows(model: dict[str, Any], prices: dict[str, Any]) -> list[tuple[str, str, int, int]]:
        modality = model["modality"]
        rows: list[tuple[str, str, int, int]] = []
        if modality == "text":
            for field, metric in (("inputPerMillionYuan", "input_tokens"), ("outputPerMillionYuan", "output_tokens")):
                value = prices.get(field)
                if value is not None:
                    rows.append((metric, "", TOKEN_UNIT, yuan_to_micros(str(value))))
        elif modality == "image":
            value = prices.get("perImageYuan")
            if value is not None:
                rows.append(("image", "", 1, yuan_to_micros(str(value))))
        elif modality == "embedding":
            value = prices.get("inputPerMillionYuan")
            if value is not None:
                rows.append(("input_tokens", "", TOKEN_UNIT, yuan_to_micros(str(value))))
        elif modality == "audio":
            capabilities = model.get("capabilities") or {}
            metric = capabilities.get("billingMetric")
            unit_size = int(capabilities.get("billingUnit") or 1)
            field = "perTenThousandCharactersYuan" if metric == "characters" else (
                "perHourYuan" if unit_size == 3600 else "perMinuteYuan"
            )
            value = prices.get(field)
            if value is not None:
                rows.append((str(metric), "", unit_size, yuan_to_micros(str(value))))
        else:
            values = prices.get("perSecondByResolution") or {}
            if not isinstance(values, dict):
                raise ApiError("视频单价必须按分辨率填写", 422, "billing_rate_invalid")
            for resolution, value in values.items():
                normalized = normalize_resolution(resolution)
                if normalized not in VIDEO_RESOLUTIONS:
                    raise ApiError("视频分辨率仅支持480p、720p、768p和1080p", 422, "billing_resolution_invalid")
                if value is not None:
                    rows.append(("video_second", normalized, 1, yuan_to_micros(str(value))))
        return rows

    def set_rate(self, alias: str, effective_month: str, prices: dict[str, Any], actor: AdminPrincipal) -> dict[str, Any]:
        validate_month(effective_month)
        if effective_month < current_month():
            raise ApiError("不能修改已结束账期的价目", 409, "billing_period_closed")
        model = self._catalog_model(alias)
        rows = self._rate_rows(model, prices)
        with self.database.connect() as connection:
            closed = connection.execute(
                "SELECT 1 FROM billing_statements WHERE billing_month=? AND status IN ('confirmed','paid') LIMIT 1",
                (effective_month,),
            ).fetchone()
            if closed:
                raise ApiError("该账期已有确认账单，不能修改价目", 409, "billing_period_closed")
            connection.execute(
                "DELETE FROM billing_model_rates WHERE model_alias=? AND effective_month=?",
                (alias, effective_month),
            )
            for metric, resolution, unit_size, amount in rows:
                connection.execute(
                    "INSERT INTO billing_model_rates(id,model_alias,metric,resolution,effective_month,unit_size,unit_price_micros,created_by) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (f"brate_{uuid.uuid4().hex}", alias, metric, resolution, effective_month, unit_size, amount, actor.id),
                )
        return self.get_rate(alias, effective_month)

    def _resolved_rates(self, alias: str, month: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT r.* FROM billing_model_rates r JOIN ("
                "SELECT metric,resolution,MAX(effective_month) AS effective_month FROM billing_model_rates "
                "WHERE model_alias=? AND effective_month<=? GROUP BY metric,resolution"
                ") latest ON latest.metric=r.metric AND latest.resolution=r.resolution "
                "AND latest.effective_month=r.effective_month WHERE r.model_alias=?",
                (alias, month, alias),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_rate(self, alias: str, month: str) -> dict[str, Any]:
        validate_month(month)
        model = self._catalog_model(alias)
        rows = self._resolved_rates(alias, month)
        prices: dict[str, Any]
        if model["modality"] == "text":
            mapped = {row["metric"]: micros_to_yuan(row["unit_price_micros"]) for row in rows}
            prices = {
                "inputPerMillionYuan": mapped.get("input_tokens"),
                "outputPerMillionYuan": mapped.get("output_tokens"),
            }
        elif model["modality"] == "image":
            row = next((item for item in rows if item["metric"] == "image"), None)
            prices = {"perImageYuan": micros_to_yuan(row["unit_price_micros"]) if row else None}
        elif model["modality"] == "embedding":
            row = next((item for item in rows if item["metric"] == "input_tokens"), None)
            prices = {"inputPerMillionYuan": micros_to_yuan(row["unit_price_micros"]) if row else None}
        elif model["modality"] == "audio":
            capabilities = model.get("capabilities") or {}
            metric = capabilities.get("billingMetric")
            unit_size = int(capabilities.get("billingUnit") or 1)
            row = next((item for item in rows if item["metric"] == metric), None)
            field = "perTenThousandCharactersYuan" if metric == "characters" else (
                "perHourYuan" if unit_size == 3600 else "perMinuteYuan"
            )
            prices = {field: micros_to_yuan(row["unit_price_micros"]) if row else None}
        else:
            mapped = {row["resolution"]: micros_to_yuan(row["unit_price_micros"]) for row in rows}
            prices = {"perSecondByResolution": {resolution: mapped.get(resolution) for resolution in VIDEO_RESOLUTIONS}}
        return {
            "model": model["alias"],
            "displayName": model["display_name"],
            "provider": model["provider"],
            "modality": model["modality"],
            "billingMetric": model.get("capabilities", {}).get("billingMetric"),
            "billingUnit": model.get("capabilities", {}).get("billingUnit"),
            "month": month,
            "sourceMonths": sorted({row["effective_month"] for row in rows}),
            "prices": prices,
        }

    def rates(self, month: str) -> list[dict[str, Any]]:
        validate_month(month)
        with self.database.connect() as connection:
            aliases = [row[0] for row in connection.execute(
                "SELECT alias FROM model_catalog WHERE enabled=1 ORDER BY modality,display_name"
            ).fetchall()]
        return [self.get_rate(alias, month) for alias in aliases]

    def _terms(self, project_name: str, month: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM project_billing_terms WHERE project_name=? AND effective_month<=? "
                "ORDER BY effective_month DESC LIMIT 1",
                (project_name, month),
            ).fetchone()
        return dict(row) if row else None

    def project_terms(self, project_name: str, month: str) -> dict[str, Any]:
        validate_month(month)
        self._project_exists(project_name)
        row = self._terms(project_name, month)
        return {
            "projectName": project_name,
            "month": month,
            "enabled": bool(row and row["enabled"]),
            "discountBps": int(row["discount_bps"]) if row else 10000,
            "sourceMonth": row["effective_month"] if row else None,
        }

    def set_project_terms(
        self, project_name: str, effective_month: str, enabled: bool, discount_bps: int, actor: AdminPrincipal
    ) -> dict[str, Any]:
        validate_month(effective_month)
        self._project_exists(project_name)
        if effective_month < current_month():
            raise ApiError("不能修改已结束账期的项目计费规则", 409, "billing_period_closed")
        with self.database.connect() as connection:
            closed = connection.execute(
                "SELECT 1 FROM billing_statements WHERE project_name=? AND billing_month=? "
                "AND status IN ('confirmed','paid')",
                (project_name, effective_month),
            ).fetchone()
            if closed:
                raise ApiError("账单已经确认，不能修改项目计费规则", 409, "billing_statement_locked")
            connection.execute(
                "INSERT INTO project_billing_terms(id,project_name,effective_month,enabled,discount_bps,updated_by) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(project_name,effective_month) DO UPDATE SET "
                "enabled=excluded.enabled,discount_bps=excluded.discount_bps,updated_by=excluded.updated_by,created_at=CURRENT_TIMESTAMP",
                (f"bterm_{uuid.uuid4().hex}", project_name, effective_month, int(enabled), discount_bps, actor.id),
            )
        return self.project_terms(project_name, effective_month)

    @staticmethod
    def _statement_number(project_name: str, month: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9]", "", project_name.upper())[:12] or "PROJECT"
        return f"RB-{month.replace('-', '')}-{safe}-{uuid.uuid4().hex[:6].upper()}"

    def _ensure_statement(self, connection: Any, project_name: str, month: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM billing_statements WHERE project_name=? AND billing_month=?",
            (project_name, month),
        ).fetchone()
        if row:
            return dict(row)
        statement_id = f"bill_{uuid.uuid4().hex}"
        connection.execute(
            "INSERT INTO billing_statements(id,statement_number,project_name,billing_month) VALUES (?,?,?,?)",
            (statement_id, self._statement_number(project_name, month), project_name, month),
        )
        return dict(connection.execute("SELECT * FROM billing_statements WHERE id=?", (statement_id,)).fetchone())

    def _rate_for(self, connection: Any, alias: str, metric: str, resolution: str, month: str) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM billing_model_rates WHERE model_alias=? AND metric=? AND resolution=? "
            "AND effective_month<=? ORDER BY effective_month DESC LIMIT 1",
            (alias, metric, resolution, month),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _amount(quantity: Decimal, unit_size: int, unit_price_micros: int) -> int:
        amount = quantity * Decimal(unit_price_micros) / Decimal(unit_size)
        return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def _model_alias(self, connection: Any, value: str) -> str | None:
        row = connection.execute(
            "SELECT alias FROM model_catalog WHERE alias=? OR upstream_model=? ORDER BY alias=? DESC LIMIT 1",
            (value, value, value),
        ).fetchone()
        return str(row["alias"]) if row else None

    def _billing_month_for(self, connection: Any, project_name: str, usage_month: str) -> tuple[str, str | None]:
        statement = connection.execute(
            "SELECT status FROM billing_statements WHERE project_name=? AND billing_month=?",
            (project_name, usage_month),
        ).fetchone()
        if statement and statement["status"] in {"confirmed", "paid"}:
            return current_month(), usage_month
        return usage_month, None

    def _upsert_item(
        self,
        connection: Any,
        *,
        source_type: str,
        source_id: str,
        api_key_id: str,
        project_name: str,
        model_alias: str | None,
        occurred_at: str,
        measurements: list[tuple[str, str, Decimal]] | None,
        pending_reason: str | None,
    ) -> None:
        usage_month = timestamp_month(occurred_at)
        terms = self._terms(project_name, usage_month)
        if not terms or not terms["enabled"]:
            return
        existing = connection.execute(
            "SELECT i.*,s.status AS statement_status FROM billing_usage_items i "
            "LEFT JOIN billing_statements s ON s.id=i.statement_id WHERE source_type=? AND source_id=?",
            (source_type, source_id),
        ).fetchone()
        if existing and existing["statement_status"] in {"confirmed", "paid"}:
            return
        billing_month, late_from = self._billing_month_for(connection, project_name, usage_month)
        item_id = existing["id"] if existing else f"bitem_{uuid.uuid4().hex}"
        status = "pending"
        components: list[tuple[str, str, Decimal, dict[str, Any], int, int]] = []
        list_amount = 0
        net_amount = 0
        reason = pending_reason
        if model_alias is None:
            reason = reason or "model_unmapped"
        elif measurements is None:
            reason = reason or "usage_unknown"
        else:
            missing: list[str] = []
            for metric, resolution, quantity in measurements:
                rate = self._rate_for(connection, model_alias, metric, resolution, usage_month)
                if rate is None:
                    missing.append(f"{metric}:{resolution}" if resolution else metric)
                    continue
                component_list = self._amount(quantity, rate["unit_size"], rate["unit_price_micros"])
                component_net = int(
                    (Decimal(component_list) * Decimal(terms["discount_bps"]) / Decimal(10000)).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                )
                components.append((metric, resolution, quantity, rate, component_list, component_net))
                list_amount += component_list
                net_amount += component_net
            if missing:
                reason = "rate_missing:" + ",".join(missing)
            else:
                status = "rated"
                reason = None
        connection.execute(
            "INSERT INTO billing_usage_items(id,source_type,source_id,api_key_id,project_name,model_alias,"
            "usage_month,billing_month,late_from_month,occurred_at,status,pending_reason,discount_bps,"
            "list_amount_micros,net_amount_micros,rated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(source_type,source_id) DO UPDATE SET model_alias=excluded.model_alias,billing_month=excluded.billing_month,"
            "late_from_month=excluded.late_from_month,status=excluded.status,pending_reason=excluded.pending_reason,"
            "discount_bps=excluded.discount_bps,list_amount_micros=excluded.list_amount_micros,"
            "net_amount_micros=excluded.net_amount_micros,rated_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP",
            (
                item_id, source_type, source_id, api_key_id, project_name, model_alias or "unmapped",
                usage_month, billing_month, late_from, occurred_at, status, reason,
                terms["discount_bps"], list_amount if status == "rated" else None,
                net_amount if status == "rated" else None,
            ),
        )
        connection.execute("DELETE FROM billing_usage_components WHERE item_id=?", (item_id,))
        if status == "rated":
            for metric, resolution, quantity, rate, component_list, component_net in components:
                connection.execute(
                    "INSERT INTO billing_usage_components(item_id,metric,resolution,quantity,unit_size,rate_id,"
                    "unit_price_micros,list_amount_micros,net_amount_micros) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        item_id, metric, resolution, format(quantity, "f"), rate["unit_size"], rate["id"],
                        rate["unit_price_micros"], component_list, component_net,
                    ),
                )
        if late_from:
            source_statement = connection.execute(
                "SELECT id FROM billing_statements WHERE project_name=? AND billing_month=?",
                (project_name, late_from),
            ).fetchone()
            if status == "rated" and net_amount:
                target = self._ensure_statement(connection, project_name, billing_month)
                connection.execute(
                    "INSERT INTO billing_adjustments(id,statement_id,amount_micros,reason,adjustment_type,"
                    "source_item_id,source_statement_id,created_by) VALUES (?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(source_item_id) DO UPDATE SET statement_id=excluded.statement_id,"
                    "amount_micros=excluded.amount_micros,reason=excluded.reason",
                    (
                        f"badj_late_{item_id}", target["id"], net_amount,
                        f"{late_from} 账期迟到用量 · {model_alias}", "late_usage", item_id,
                        source_statement["id"] if source_statement else None, "system",
                    ),
                )
            else:
                connection.execute(
                    "DELETE FROM billing_adjustments WHERE source_item_id=?", (item_id,)
                )

    @staticmethod
    def _relay_measurements(row: dict[str, Any]) -> tuple[list[tuple[str, str, Decimal]] | None, str | None]:
        if row["modality"] == "text":
            if row["input_tokens"] is None or row["output_tokens"] is None:
                return None, "usage_unknown"
            return [
                ("input_tokens", "", Decimal(row["input_tokens"])),
                ("output_tokens", "", Decimal(row["output_tokens"])),
            ], None
        if row["modality"] == "image":
            if row["generated_images"] is None:
                return None, "usage_unknown"
            return [("image", "", Decimal(row["generated_images"]))], None
        if row["modality"] == "embedding":
            if row["input_tokens"] is None:
                return None, "usage_unknown"
            return [("input_tokens", "", Decimal(row["input_tokens"]))], None
        if row["modality"] == "audio":
            capabilities = _loaded(row.get("capabilities_json"), {})
            metric = capabilities.get("billingMetric")
            if metric == "characters":
                if row.get("input_characters") is None:
                    return None, "usage_unknown"
                return [("characters", "", Decimal(row["input_characters"]))], None
            if row.get("audio_seconds") is None or Decimal(str(row["audio_seconds"])) <= 0:
                return None, "usage_unknown"
            return [("audio_second", "", Decimal(str(row["audio_seconds"])))], None
        if row["video_seconds"] is None or Decimal(str(row["video_seconds"])) <= 0:
            return None, "usage_unknown"
        billing_meta = _loaded(row.get("billing_metadata_json"), {})
        provider_meta = _loaded(row.get("metadata_json"), {})
        resolution = normalize_resolution(
            provider_meta.get("resolution") or billing_meta.get("resolution"),
            row.get("video_width"), row.get("video_height"),
        )
        if not resolution:
            return None, "resolution_unknown"
        return [("video_second", resolution, Decimal(str(row["video_seconds"])))], None

    def _collect_sources(self, connection: Any) -> set[tuple[str, str]]:
        touched: set[tuple[str, str]] = set()
        relay_rows = connection.execute(
            "SELECT u.*,m.modality,m.capabilities_json,t.metadata_json,t.billing_metadata_json FROM inference_usage u "
            "JOIN model_catalog m ON m.alias=u.model_alias LEFT JOIN inference_tasks t ON t.id=u.task_id "
            "WHERE u.status='succeeded' ORDER BY u.created_at"
        ).fetchall()
        for raw in relay_rows:
            row = dict(raw)
            measurements, reason = self._relay_measurements(row)
            self._upsert_item(
                connection,
                source_type="relay", source_id=row["id"], api_key_id=row["api_key_id"],
                project_name=row["project_name"], model_alias=row["model_alias"],
                occurred_at=row["created_at"], measurements=measurements, pending_reason=reason,
            )
            touched.add((row["project_name"], timestamp_month(row["created_at"])))
        legacy_rows = connection.execute(
            "SELECT u.*,t.record_json,t.status AS task_status FROM video_usage u "
            "LEFT JOIN video_tasks t ON t.api_key_id=u.api_key_id AND t.task_id=u.task_id ORDER BY u.created_at"
        ).fetchall()
        for raw in legacy_rows:
            row = dict(raw)
            record = _loaded(row.get("record_json"), {})
            alias = self._model_alias(connection, row["model"])
            status = str(row.get("task_status") or record.get("status") or "").lower()
            # A video_usage row can be written before a legacy task reaches its
            # terminal state. Failed, canceled and in-flight tasks are not usage
            # gaps: they are deliberately excluded from billing. Confirmation
            # separately checks for unfinished tasks in the statement period.
            if status and status not in {"succeeded", "success"}:
                continue
            measurements = None
            reason = None
            try:
                duration = Decimal(str(record.get("duration")))
            except (InvalidOperation, TypeError):
                duration = Decimal(0)
            resolution = normalize_resolution(record.get("resolution"))
            if reason is None and duration > 0 and resolution:
                measurements = [("video_second", resolution, duration)]
            elif reason is None:
                reason = "usage_unknown" if duration <= 0 else "resolution_unknown"
            self._upsert_item(
                connection,
                source_type="legacy_video", source_id=f"{row['api_key_id']}:{row['task_id']}",
                api_key_id=row["api_key_id"], project_name=row["project_name"], model_alias=alias,
                occurred_at=row["created_at"], measurements=measurements, pending_reason=reason,
            )
            touched.add((row["project_name"], timestamp_month(row["created_at"])))
        return touched

    def _rebuild_statement(self, connection: Any, project_name: str, month: str) -> dict[str, Any] | None:
        terms = self._terms(project_name, month)
        existing = connection.execute(
            "SELECT * FROM billing_statements WHERE project_name=? AND billing_month=?",
            (project_name, month),
        ).fetchone()
        if (not terms or not terms["enabled"]) and existing is None:
            return None
        statement = dict(existing) if existing else self._ensure_statement(connection, project_name, month)
        if statement["status"] != "draft":
            return statement
        statement_id = statement["id"]
        if not terms or not terms["enabled"]:
            connection.execute("DELETE FROM billing_statement_lines WHERE statement_id=?", (statement_id,))
            connection.execute("UPDATE billing_usage_items SET statement_id=NULL WHERE statement_id=?", (statement_id,))
            connection.execute(
                "UPDATE billing_statements SET subtotal_micros=0,discount_micros=0,adjustment_micros=0,"
                "total_micros=0,pending_count=0,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (statement_id,),
            )
            return dict(connection.execute("SELECT * FROM billing_statements WHERE id=?", (statement_id,)).fetchone())
        connection.execute("DELETE FROM billing_statement_lines WHERE statement_id=?", (statement_id,))
        connection.execute(
            "UPDATE billing_usage_items SET statement_id=NULL WHERE statement_id=?", (statement_id,)
        )
        rows = connection.execute(
            "SELECT c.*,i.model_alias FROM billing_usage_components c JOIN billing_usage_items i ON i.id=c.item_id "
            "WHERE i.project_name=? AND i.billing_month=? AND i.status='rated' AND i.late_from_month IS NULL",
            (project_name, month),
        ).fetchall()
        grouped: dict[tuple[str, str, str, int, int], dict[str, Any]] = {}
        for row in rows:
            key = (row["model_alias"], row["metric"], row["resolution"], row["unit_size"], row["unit_price_micros"])
            current = grouped.setdefault(key, {"quantity": Decimal(0), "list": 0, "net": 0})
            current["quantity"] += Decimal(row["quantity"])
            current["list"] += row["list_amount_micros"]
            current["net"] += row["net_amount_micros"]
        for (alias, metric, resolution, unit_size, unit_price), values in grouped.items():
            connection.execute(
                "INSERT INTO billing_statement_lines(id,statement_id,model_alias,metric,resolution,quantity,unit_size,"
                "unit_price_micros,list_amount_micros,net_amount_micros) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    f"bline_{uuid.uuid4().hex}", statement_id, alias, metric, resolution,
                    format(values["quantity"], "f"), unit_size, unit_price, values["list"], values["net"],
                ),
            )
        connection.execute(
            "UPDATE billing_usage_items SET statement_id=? WHERE project_name=? AND billing_month=?",
            (statement_id, project_name, month),
        )
        totals = connection.execute(
            "SELECT COALESCE(SUM(list_amount_micros),0) AS subtotal,COALESCE(SUM(net_amount_micros),0) AS net "
            "FROM billing_usage_items WHERE project_name=? AND billing_month=? AND status='rated' "
            "AND late_from_month IS NULL",
            # Late usage is represented by a system adjustment so confirmed history
            # remains immutable and the next open statement still explains the delta.
            (project_name, month),
        ).fetchone()
        pending = connection.execute(
            "SELECT COUNT(*) FROM billing_usage_items WHERE project_name=? AND billing_month=? AND status='pending'",
            (project_name, month),
        ).fetchone()[0]
        adjustment = connection.execute(
            "SELECT COALESCE(SUM(amount_micros),0) FROM billing_adjustments WHERE statement_id=?",
            (statement_id,),
        ).fetchone()[0]
        subtotal = int(totals["subtotal"])
        net = int(totals["net"])
        connection.execute(
            "UPDATE billing_statements SET subtotal_micros=?,discount_micros=?,adjustment_micros=?,"
            "total_micros=?,pending_count=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (subtotal, subtotal - net, adjustment, net + adjustment, pending, statement_id),
        )
        return dict(connection.execute("SELECT * FROM billing_statements WHERE id=?", (statement_id,)).fetchone())

    async def reconcile(self, project_name: str | None = None, month: str | None = None) -> None:
        async with self._lock:
            with self.database.connect() as connection:
                touched = self._collect_sources(connection)
                if project_name and month:
                    touched.add((project_name, validate_month(month)))
                current = current_month()
                active = connection.execute(
                    "SELECT DISTINCT project_name FROM project_billing_terms WHERE enabled=1 AND effective_month<=?",
                    (current,),
                ).fetchall()
                touched.update((row["project_name"], current) for row in active)
                previous = previous_month(current)
                touched.update((row["project_name"], previous) for row in active)
                for project, billing_month in sorted(touched):
                    if project_name and project != project_name:
                        continue
                    if month and billing_month != month:
                        continue
                    self._rebuild_statement(connection, project, billing_month)

    @staticmethod
    def _statement_payload(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"], "number": row["statement_number"], "projectName": row["project_name"],
            "month": row["billing_month"], "status": row["status"], "currency": row["currency"],
            "subtotalYuan": micros_to_yuan(row["subtotal_micros"]),
            "discountYuan": micros_to_yuan(row["discount_micros"]),
            "adjustmentYuan": micros_to_yuan(row["adjustment_micros"]),
            "totalYuan": micros_to_yuan(row["total_micros"]), "pendingCount": row["pending_count"],
            "generatedAt": row["generated_at"], "updatedAt": row["updated_at"],
            "confirmedAt": row["confirmed_at"], "paidAt": row["paid_at"],
            "paymentReference": row["payment_reference"], "paymentNote": row["payment_note"],
        }

    async def preview(self, project_name: str, month: str) -> dict[str, Any]:
        validate_month(month)
        self._project_exists(project_name)
        await self.reconcile(project_name, month)
        terms = self.project_terms(project_name, month)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM billing_statements WHERE project_name=? AND billing_month=?",
                (project_name, month),
            ).fetchone()
        return {"terms": terms, "statement": self._statement_payload(dict(row)) if row else None}

    def statements(self, project_name: str | None, month: str | None, status: str | None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (("project_name", project_name), ("billing_month", month), ("status", status)):
            if value:
                clauses.append(f"{column}=?")
                params.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM billing_statements" + where + " ORDER BY billing_month DESC,project_name", params
            ).fetchall()
        return [self._statement_payload(dict(row)) for row in rows]

    def statement(self, statement_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM billing_statements WHERE id=?", (statement_id,)).fetchone()
            if row is None:
                raise ApiError("账单不存在", 404, "billing_statement_not_found")
            lines = connection.execute(
                "SELECT * FROM billing_statement_lines WHERE statement_id=? ORDER BY model_alias,metric,resolution",
                (statement_id,),
            ).fetchall()
            adjustments = connection.execute(
                "SELECT * FROM billing_adjustments WHERE statement_id=? ORDER BY created_at,id", (statement_id,)
            ).fetchall()
            pending = connection.execute(
                "SELECT model_alias,pending_reason,COUNT(*) AS count FROM billing_usage_items "
                "WHERE statement_id=? AND status='pending' GROUP BY model_alias,pending_reason",
                (statement_id,),
            ).fetchall()
        payload = self._statement_payload(dict(row))
        payload["lines"] = [
            {
                "id": item["id"], "model": item["model_alias"], "metric": item["metric"],
                "resolution": item["resolution"] or None, "quantity": item["quantity"],
                "unitSize": item["unit_size"], "unitPriceYuan": micros_to_yuan(item["unit_price_micros"]),
                "listAmountYuan": micros_to_yuan(item["list_amount_micros"]),
                "netAmountYuan": micros_to_yuan(item["net_amount_micros"]),
            }
            for item in lines
        ]
        payload["adjustments"] = [
            {
                "id": item["id"], "amountYuan": micros_to_yuan(item["amount_micros"]),
                "reason": item["reason"], "type": item["adjustment_type"],
                "createdAt": item["created_at"],
            }
            for item in adjustments
        ]
        payload["pending"] = [dict(item) for item in pending]
        return payload

    def _draft(self, connection: Any, statement_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM billing_statements WHERE id=?", (statement_id,)).fetchone()
        if row is None:
            raise ApiError("账单不存在", 404, "billing_statement_not_found")
        if row["status"] != "draft":
            raise ApiError("账单已锁定，不能修改", 409, "billing_statement_locked")
        return dict(row)

    def add_adjustment(self, statement_id: str, amount_yuan: str, reason: str, actor: AdminPrincipal) -> dict[str, Any]:
        amount = signed_yuan_to_micros(amount_yuan)
        reason = reason.strip()
        if not reason:
            raise ApiError("必须填写调整原因", 422, "billing_adjustment_reason_required")
        with self.database.connect() as connection:
            statement = self._draft(connection, statement_id)
            adjustment_id = f"badj_{uuid.uuid4().hex}"
            connection.execute(
                "INSERT INTO billing_adjustments(id,statement_id,amount_micros,reason,created_by) VALUES (?,?,?,?,?)",
                (adjustment_id, statement_id, amount, reason[:500], actor.id),
            )
            self._rebuild_statement(connection, statement["project_name"], statement["billing_month"])
        return self.statement(statement_id)

    def delete_adjustment(self, statement_id: str, adjustment_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            statement = self._draft(connection, statement_id)
            cursor = connection.execute(
                "DELETE FROM billing_adjustments WHERE id=? AND statement_id=? AND adjustment_type='manual'",
                (adjustment_id, statement_id),
            )
            if not cursor.rowcount:
                raise ApiError("调整项不存在", 404, "billing_adjustment_not_found")
            self._rebuild_statement(connection, statement["project_name"], statement["billing_month"])
        return self.statement(statement_id)

    def confirm(self, statement_id: str, actor: AdminPrincipal) -> dict[str, Any]:
        with self.database.connect() as connection:
            statement = self._draft(connection, statement_id)
            if statement["billing_month"] >= current_month():
                raise ApiError("当前自然月账单只能预览，月结后才能确认", 409, "billing_current_month_open")
            rebuilt = self._rebuild_statement(connection, statement["project_name"], statement["billing_month"])
            if rebuilt and rebuilt["pending_count"]:
                raise ApiError("账单仍有待计价用量，暂时不能确认", 409, "billing_usage_pending", details={"pendingCount": rebuilt["pending_count"]})
            start, end = month_bounds_utc(statement["billing_month"])
            active_relay = connection.execute(
                "SELECT COUNT(*) FROM inference_tasks WHERE project_name=? AND status IN ('queued','running') "
                "AND datetime(created_at,'unixepoch')>=? AND datetime(created_at,'unixepoch')<?",
                (statement["project_name"], start, end),
            ).fetchone()[0]
            active_legacy = connection.execute(
                "SELECT COUNT(*) FROM video_tasks WHERE project_name=? AND status IN ('queued','running') "
                "AND datetime(created_at/1000,'unixepoch')>=? AND datetime(created_at/1000,'unixepoch')<?",
                (statement["project_name"], start, end),
            ).fetchone()[0]
            if active_relay or active_legacy:
                raise ApiError("账期内仍有未完成任务，暂时不能确认", 409, "billing_tasks_active", details={"activeTasks": active_relay + active_legacy})
            connection.execute(
                "UPDATE billing_statements SET status='confirmed',confirmed_at=CURRENT_TIMESTAMP,confirmed_by=?,"
                "updated_at=CURRENT_TIMESTAMP WHERE id=?", (actor.id, statement_id)
            )
        return self.statement(statement_id)

    def mark_paid(self, statement_id: str, paid_at: str | None, reference: str | None, note: str | None, actor: AdminPrincipal) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT status FROM billing_statements WHERE id=?", (statement_id,)).fetchone()
            if row is None:
                raise ApiError("账单不存在", 404, "billing_statement_not_found")
            if row["status"] != "confirmed":
                raise ApiError("只有已确认账单可以标记为已支付", 409, "billing_statement_not_confirmed")
            payment_time = paid_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if paid_at:
                try:
                    datetime.fromisoformat(paid_at.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ApiError("支付日期格式无效", 422, "billing_paid_at_invalid") from exc
            connection.execute(
                "UPDATE billing_statements SET status='paid',paid_at=?,paid_by=?,payment_reference=?,payment_note=?,"
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (payment_time, actor.id, (reference or "").strip()[:100] or None, (note or "").strip()[:500] or None, statement_id),
            )
        return self.statement(statement_id)

    def csv_bytes(self, statement_id: str) -> bytes:
        statement = self.statement(statement_id)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["账单号", statement["number"], "客户项目", statement["projectName"], "账期", statement["month"], "状态", statement["status"]])
        writer.writerow(["模型", "指标", "分辨率", "数量", "计价单位", "单价（元）", "原价金额（元）", "折后金额（元）"])
        labels = {"input_tokens": "输入Token", "output_tokens": "输出Token", "image": "图片", "video_second": "视频秒数"}
        for line in statement["lines"]:
            model = str(line["model"])
            if model[:1] in {"=", "+", "-", "@"}:
                model = "'" + model
            unit = "100万Token" if "tokens" in line["metric"] else ("张" if line["metric"] == "image" else "秒")
            writer.writerow([model, labels.get(line["metric"], line["metric"]), line["resolution"] or "", line["quantity"], unit, line["unitPriceYuan"], line["listAmountYuan"], line["netAmountYuan"]])
        for adjustment in statement["adjustments"]:
            reason = str(adjustment["reason"])
            if reason[:1] in {"=", "+", "-", "@"}:
                reason = "'" + reason
            writer.writerow(["调整项", reason, "", "", "", "", "", adjustment["amountYuan"]])
        writer.writerow([])
        writer.writerow(["原价合计", statement["subtotalYuan"], "折扣优惠", statement["discountYuan"], "调整合计", statement["adjustmentYuan"], "应付合计", statement["totalYuan"]])
        return ("\ufeff" + output.getvalue()).encode("utf-8")
