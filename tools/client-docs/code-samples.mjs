// Generate examples only; the reader never executes requests or accepts API keys.
export function curlSamples(text) {
  const shell = { language: 'shell', label: 'Shell', text };
  if (!text.trimStart().startsWith('curl') || text.includes('-F ') || text.match(/\bcurl\b/g)?.length !== 1) return [shell];
  const endpoint = text.match(/["']\$BASE_URL([^"']+)["']/)?.[1];
  if (!endpoint) return [shell];
  const raw = text.match(/-d '([\s\S]+)'/)?.[1];
  let payload;
  if (raw) { try { payload = JSON.parse(raw); } catch { return [shell]; } }
  const method = text.match(/-X (\w+)/)?.[1] || (payload ? 'POST' : 'GET');
  const headers = Object.fromEntries([...text.matchAll(/-H "([^:]+): ([^"]+)"/g)].map(m => [m[1], m[2]]));
  const output = text.match(/--output ([\w.-]+)/)?.[1];
  const stream = text.includes('stream": true');
  const jsHeaders = { ...headers, Authorization: 'Bearer REPLACE_API_KEY' };
  const js = [
    'const apiKey = process.env.API_KEY; // 仅在服务器保存',
    'const endpoint = ' + JSON.stringify(endpoint) + '.replace("$TASK_ID", process.env.TASK_ID ?? "task_id");',
    'const headers = ' + JSON.stringify(jsHeaders, null, 2) + ';',
    'headers.Authorization = "Bearer " + apiKey;',
    ...(payload ? ['const body = ' + JSON.stringify(payload, null, 2) + ';'] : []),
    'const response = await fetch("https://api.richbest.cn" + endpoint, {',
    '  method: ' + JSON.stringify(method) + ', headers,',
    ...(payload ? ['  body: JSON.stringify(body),'] : []),
    '});',
    'if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);',
    ...(stream ? ['// 原始 SSE 数据；生产代码须解析事件并处理正常结束/错误。', 'for await (const chunk of response.body) process.stdout.write(chunk);'] :
      output ? ['const { writeFile } = await import("node:fs/promises");', 'await writeFile(' + JSON.stringify(output) + ', Buffer.from(await response.arrayBuffer()));'] :
        method === 'DELETE' ? ['console.log(response.status); // 204 时不要解析 JSON'] : ['console.log(await response.json());']),
  ].join('\n');
  const pythonHeaders = { ...headers, Authorization: 'Bearer REPLACE_API_KEY' };
  const python = [
    'import json', 'import os', 'import urllib.request',
    'endpoint = ' + JSON.stringify(endpoint) + '.replace("$TASK_ID", os.environ.get("TASK_ID", "task_id"))',
    'headers = json.loads(' + JSON.stringify(JSON.stringify(pythonHeaders)) + ')',
    'headers["Authorization"] = "Bearer " + os.environ["API_KEY"]',
    ...(payload ? ['payload = json.loads(' + JSON.stringify(JSON.stringify(payload)) + ')', 'data = json.dumps(payload, ensure_ascii=False).encode("utf-8")'] : ['data = None']),
    'request = urllib.request.Request(',
    '    "https://api.richbest.cn" + endpoint, data=data, headers=headers, method=' + JSON.stringify(method),
    ')',
    '//PLACEHOLDER',
    'with urllib.request.urlopen(request, timeout=1900) as response:',
    ...(stream ? ['    # 原始 SSE；生产代码须处理事件与终态，不自动重发。', '    for line in response:', '        print(line.decode("utf-8"), end="", flush=True)'] :
      output ? ['    with open(' + JSON.stringify(output) + ', "wb") as file:', '        file.write(response.read())'] :
        method === 'DELETE' ? ['    print(response.status)  # 204 时无 JSON 响应体'] : ['    print(json.loads(response.read()))']),
  ].filter(line => line !== '//PLACEHOLDER').join('\n');
  return [shell, { language: 'javascript', label: 'JavaScript', text: js }, { language: 'python', label: 'Python', text: python }];
}
