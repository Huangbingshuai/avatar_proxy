from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from ..admin_auth import AdminPrincipal
from ..billing import current_month
from ..schemas import (
    BillingAdjustmentCreate,
    BillingPaymentCreate,
    BillingRateUpdate,
    BillingSensitiveAction,
    ProjectBillingUpdate,
)
from ..security import BusinessAdminDependency


router = APIRouter(prefix="/api/internal/billing", tags=["项目计费账单"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _reauth(request: Request, principal: AdminPrincipal, password: str, action: str) -> None:
    request.app.state.admin_auth.verify_current_password(
        principal, password, _ip(request), _ua(request), action
    )


def _audit(
    request: Request,
    principal: AdminPrincipal,
    action: str,
    target_type: str,
    target_id: str,
    *,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    request.app.state.database.write_admin_audit(
        actor=principal.username,
        actor_id=principal.id,
        source_ip=_ip(request),
        user_agent=_ua(request),
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=before,
        after=after,
    )


@router.get("/rates")
def list_rates(
    request: Request,
    _: BusinessAdminDependency,
    month: str = Query(default_factory=current_month, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
) -> dict:
    return {"month": month, "rates": request.app.state.billing.rates(month)}


@router.put("/rates/{model_alias}")
def update_rate(
    model_alias: str,
    payload: BillingRateUpdate,
    request: Request,
    principal: BusinessAdminDependency,
) -> dict:
    _reauth(request, principal, payload.current_password, "billing.rate.update")
    before = request.app.state.billing.get_rate(model_alias, payload.effective_month)
    rate = request.app.state.billing.set_rate(
        model_alias, payload.effective_month, payload.prices, principal
    )
    _audit(
        request,
        principal,
        "billing.rate.update",
        "billing_model_rate",
        f"{model_alias}:{payload.effective_month}",
        before={"prices": before["prices"]},
        after={"prices": rate["prices"]},
    )
    return {"rate": rate}


@router.get("/projects/{project_name}")
def get_project_billing(
    project_name: str,
    request: Request,
    _: BusinessAdminDependency,
    month: str = Query(default_factory=current_month, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
) -> dict:
    return {"billing": request.app.state.billing.project_terms(project_name, month)}


@router.put("/projects/{project_name}")
def update_project_billing(
    project_name: str,
    payload: ProjectBillingUpdate,
    request: Request,
    principal: BusinessAdminDependency,
) -> dict:
    _reauth(request, principal, payload.current_password, "billing.project.update")
    before = request.app.state.billing.project_terms(project_name, payload.effective_month)
    billing = request.app.state.billing.set_project_terms(
        project_name, payload.effective_month, payload.enabled, payload.discount_bps, principal
    )
    _audit(
        request,
        principal,
        "billing.project.update",
        "project",
        project_name,
        before=before,
        after=billing,
    )
    return {"billing": billing}


@router.get("/preview")
async def billing_preview(
    request: Request,
    _: BusinessAdminDependency,
    project_name: str = Query(alias="projectName", min_length=1, max_length=64),
    month: str = Query(default_factory=current_month, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
) -> dict:
    return await request.app.state.billing.preview(project_name, month)


@router.get("/statements")
def list_statements(
    request: Request,
    _: BusinessAdminDependency,
    project_name: str | None = Query(default=None, alias="projectName", max_length=64),
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    status: str | None = Query(default=None, pattern=r"^(draft|confirmed|paid)$"),
) -> dict:
    return {
        "statements": request.app.state.billing.statements(project_name, month, status)
    }


@router.get("/statements/{statement_id}")
def get_statement(
    statement_id: str, request: Request, _: BusinessAdminDependency
) -> dict:
    return {"statement": request.app.state.billing.statement(statement_id)}


@router.post("/statements/{statement_id}/recalculate")
async def recalculate_statement(
    statement_id: str, request: Request, principal: BusinessAdminDependency
) -> dict:
    before = request.app.state.billing.statement(statement_id)
    await request.app.state.billing.reconcile(before["projectName"], before["month"])
    statement = request.app.state.billing.statement(statement_id)
    _audit(
        request,
        principal,
        "billing.statement.recalculate",
        "billing_statement",
        statement_id,
        before={"totalYuan": before["totalYuan"], "pendingCount": before["pendingCount"]},
        after={"totalYuan": statement["totalYuan"], "pendingCount": statement["pendingCount"]},
    )
    return {"statement": statement}


@router.post("/statements/{statement_id}/adjustments")
def add_adjustment(
    statement_id: str,
    payload: BillingAdjustmentCreate,
    request: Request,
    principal: BusinessAdminDependency,
) -> dict:
    _reauth(request, principal, payload.current_password, "billing.adjustment.create")
    statement = request.app.state.billing.add_adjustment(
        statement_id, payload.amount_yuan, payload.reason, principal
    )
    _audit(
        request,
        principal,
        "billing.adjustment.create",
        "billing_statement",
        statement_id,
        after={"amountYuan": payload.amount_yuan, "reason": payload.reason, "totalYuan": statement["totalYuan"]},
    )
    return {"statement": statement}


@router.delete("/statements/{statement_id}/adjustments/{adjustment_id}")
def delete_adjustment(
    statement_id: str,
    adjustment_id: str,
    payload: BillingSensitiveAction,
    request: Request,
    principal: BusinessAdminDependency,
) -> dict:
    _reauth(request, principal, payload.current_password, "billing.adjustment.delete")
    statement = request.app.state.billing.delete_adjustment(statement_id, adjustment_id)
    _audit(
        request,
        principal,
        "billing.adjustment.delete",
        "billing_adjustment",
        adjustment_id,
        after={"deleted": True, "statementId": statement_id},
    )
    return {"statement": statement}


@router.post("/statements/{statement_id}/confirm")
def confirm_statement(
    statement_id: str,
    payload: BillingSensitiveAction,
    request: Request,
    principal: BusinessAdminDependency,
) -> dict:
    _reauth(request, principal, payload.current_password, "billing.statement.confirm")
    statement = request.app.state.billing.confirm(statement_id, principal)
    _audit(
        request,
        principal,
        "billing.statement.confirm",
        "billing_statement",
        statement_id,
        after={"status": "confirmed", "totalYuan": statement["totalYuan"]},
    )
    return {"statement": statement}


@router.post("/statements/{statement_id}/mark-paid")
def mark_statement_paid(
    statement_id: str,
    payload: BillingPaymentCreate,
    request: Request,
    principal: BusinessAdminDependency,
) -> dict:
    _reauth(request, principal, payload.current_password, "billing.statement.mark_paid")
    statement = request.app.state.billing.mark_paid(
        statement_id, payload.paid_at, payload.reference, payload.note, principal
    )
    _audit(
        request,
        principal,
        "billing.statement.mark_paid",
        "billing_statement",
        statement_id,
        after={"status": "paid", "paidAt": statement["paidAt"], "paymentReference": statement["paymentReference"]},
    )
    return {"statement": statement}


@router.get("/statements/{statement_id}/export.csv")
def export_statement(
    statement_id: str, request: Request, _: BusinessAdminDependency
) -> Response:
    statement = request.app.state.billing.statement(statement_id)
    content = request.app.state.billing.csv_bytes(statement_id)
    filename = f"billing-{statement['month']}-{statement['projectName']}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
