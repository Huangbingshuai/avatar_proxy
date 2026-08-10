import { badJson, proxyAction, readJson } from "@/lib/route-helpers";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const body: Record<string, unknown> = {
    PageNumber: Number(url.searchParams.get("page") || 1),
    PageSize: Math.min(Number(url.searchParams.get("page_size") || 20), 100),
    SortBy: url.searchParams.get("sort_by") || "CreateTime",
    SortOrder: url.searchParams.get("sort_order") || "Desc",
    Filter: {
      GroupIds: url.searchParams.getAll("group_id"),
      GroupType: "AIGC",
      Statuses: url.searchParams.getAll("status"),
      Name: url.searchParams.get("name") || undefined,
    },
  };
  return proxyAction(request, "ListAssets", body);
}

export async function POST(request: Request) {
  const body = await readJson(request);
  if (!body) return badJson();
  return proxyAction(request, "CreateAsset", {
    GroupId: body.group_id,
    URL: body.url,
    AssetType: body.asset_type,
    Name: body.name,
  });
}
