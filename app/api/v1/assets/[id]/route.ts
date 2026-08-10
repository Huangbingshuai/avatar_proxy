import { badJson, proxyAction, readJson } from "@/lib/route-helpers";

type Context = { params: Promise<{ id: string }> };

export async function GET(request: Request, context: Context) {
  return proxyAction(request, "GetAsset", { Id: (await context.params).id });
}

export async function PATCH(request: Request, context: Context) {
  const body = await readJson(request);
  if (!body) return badJson();
  return proxyAction(request, "UpdateAsset", { Id: (await context.params).id, Name: body.name });
}

export async function DELETE(request: Request, context: Context) {
  return proxyAction(request, "DeleteAsset", { Id: (await context.params).id });
}
