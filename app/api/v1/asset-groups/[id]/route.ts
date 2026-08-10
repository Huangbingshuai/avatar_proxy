import { badJson, proxyAction, readJson } from "@/lib/route-helpers";

type Context = { params: Promise<{ id: string }> };

export async function GET(request: Request, context: Context) {
  return proxyAction(request, "GetAssetGroup", { Id: (await context.params).id });
}

export async function PATCH(request: Request, context: Context) {
  const body = await readJson(request);
  if (!body) return badJson();
  return proxyAction(request, "UpdateAssetGroup", {
    Id: (await context.params).id,
    Name: body.name,
    Description: body.description,
  });
}

export async function DELETE(request: Request, context: Context) {
  return proxyAction(request, "DeleteAssetGroup", { Id: (await context.params).id });
}
