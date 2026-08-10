import { badJson, proxyAction, readJson } from "@/lib/route-helpers";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const body: Record<string, unknown> = {
    PageNumber: Number(url.searchParams.get("page") || 1),
    PageSize: Math.min(Number(url.searchParams.get("page_size") || 20), 100),
    Filter: {
      Name: url.searchParams.get("name") || undefined,
      GroupType: "AIGC",
      GroupIds: url.searchParams.getAll("group_id"),
    },
  };
  return proxyAction(request, "ListAssetGroups", body);
}

export async function POST(request: Request) {
  const body = await readJson(request);
  if (!body) return badJson();
  return proxyAction(request, "CreateAssetGroup", {
    Name: body.name,
    Description: body.description ?? "",
    GroupType: "AIGC",
  });
}
