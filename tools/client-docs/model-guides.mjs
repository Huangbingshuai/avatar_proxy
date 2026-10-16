const tick = String.fromCharCode(96);
const inline = value => tick + value + tick;
const fence = (language, body) => tick.repeat(3) + language + '\n' + body + '\n' + tick.repeat(3);
const json = body => fence('json', JSON.stringify(body, null, 2));
const table = rows => ['| 参数 | 必填 | 类型与说明 |', '|---|---|---|', ...rows.map(row => '| ' + row.join(' | ') + ' |')].join('\n');
export const modelPageId = alias => 'model-' + alias;
export function modelFamily(model) {
  if (model.id.startsWith('gpt-image')) return 'GPT Image';
  if (model.id.startsWith('doubao-seedream')) return 'Doubao Seedream';
  if (model.id.startsWith('dola-seedream')) return 'Dola Seedream';
  if (model.id.startsWith('doubao-seedance')) return 'Doubao Seedance';
  if (model.id.startsWith('dreamina-seedance')) return 'Dreamina Seedance';
  if (model.id.startsWith('deepseek')) return 'DeepSeek';
  if (model.id.startsWith('glm-')) return 'GLM';
  if (model.modality === 'text') return 'Doubao Seed';
  if (model.modality === 'audio') return '语音与音频模型';
  if (model.modality === 'embedding') return '向量模型';
  if (model.id.startsWith('wan')) return 'Wan';
  return 'MiniMax';
}
export function section(source, heading) {
  const lines = source.split('\n');
  const start = lines.findIndex(line => line === heading);
  if (start < 0) throw new Error('Missing reference section: ' + heading);
  const depth = heading.match(/^#+/)[0].length;
  let end = start + 1;
  while (end < lines.length && !new RegExp('^#{1,' + depth + '} ').test(lines[end])) end++;
  return lines.slice(start + 1, end).join('\n').trim();
}
const curl = (endpoint, body, { stream = false, idempotency = false, output = '' } = {}) =>
  fence('bash', [
    'curl ' + (stream ? '-N ' : '') + '"$BASE_URL' + endpoint + '" \\',
    '  -H "Authorization: Bearer $API_KEY" \\',
    '  -H "Content-Type: application/json" \\',
    ...(idempotency ? ['  -H "Idempotency-Key: customer-order-unique-id" \\'] : []),
    "  -d '" + JSON.stringify(body, null, 2) + "'" + (output ? ' \\\n  --output ' + output : ''),
  ].join('\n'));
const modelField = alias => [inline('model'), '是', '固定填写 ' + inline(alias) + '，最长 128 个字符'];

function textGuide(model) {
  const { id, capabilities: caps } = model;
  if (caps.translation) return [
    '### 接口', inline('POST /v1/responses'),
    '只支持非流式 Responses 翻译，不支持 Chat Completions。每个文本项必须提供目标语言。',
    '### 请求示例', curl('/v1/responses', { model: id, input: [{ role: 'user', content: [{
      type: 'input_text', text: '你好', translation_options: { source_language: 'zh', target_language: 'en' },
    }] }], stream: false }),
    '### 请求参数', table([modelField(id),
      [inline('input'), '是', '结构化消息数组，文本项使用 ' + inline('input_text')],
      [inline('translation_options.target_language'), '是', '字符串，目标语言，例如 en'],
      [inline('translation_options.source_language'), '否', '源语言；省略时自动识别'],
      [inline('stream'), '否', '仅支持 false'],
    ]),
    '### 返回结果', '按 Responses 的 ' + inline('output') + ' 消息读取 ' + inline('output_text') + ' 内容，不使用 Chat 的 choices 结构。用量只包含实际返回的 usage。',
  ].join('\n\n');
  const parts = [
    '### 接口', inline('POST /v1/chat/completions') + ' · ' + inline('POST /v1/responses'),
    '### 请求示例', curl('/v1/chat/completions', { model: id, messages: [{ role: 'user', content: '用一句话介绍你自己' }], stream: false }),
    '### 请求参数', table([modelField(id),
      [inline('messages'), 'Chat 必填', '消息数组，包含 role 和 content'],
      [inline('input'), 'Responses 必填', '文本或结构化输入；不要同时套用 Chat 消息体'],
      [inline('stream'), '否', '布尔值；true 为 SSE，false 为同步 JSON'],
      [inline('stream_options'), '否', 'Chat 流式用量可使用 ' + inline('{"include_usage":true}')],
      [inline('max_completion_tokens') + ' / ' + inline('max_tokens'), '否', 'Chat 输出上限，具体支持情况由模型决定'],
      [inline('max_output_tokens'), '否', 'Responses 输出上限，具体支持情况由模型决定'],
      [inline('temperature') + ' / ' + inline('top_p'), '否', '采样参数，模型支持范围以实际能力为准'],
    ]),
    '顶层可接收字段完整列表见[文本通用参数](text.md#chat-completions)。未列入白名单的字段返回 422。',
    '### 流式调用', curl('/v1/chat/completions', { model: id, messages: [{ role: 'user', content: '用一句话描述春天' }], stream: true, stream_options: { include_usage: true } }, { stream: true }),
    '逐段消费 ' + inline('choices[].delta') + '。不能等待整个响应完成后才解析，也不能将中断当作完整成功。',
    '### Responses 调用', curl('/v1/responses', { model: id, input: '列出三条产品发布检查项', stream: false }),
  ];
  if (caps.imageInput) parts.push('### 图片理解', curl('/v1/chat/completions', { model: id, messages: [{ role: 'user', content: [
    { type: 'text', text: '描述图片中的商品' },
    { type: 'image_url', image_url: { url: 'https://customer.example.com/product.jpg' } },
  ] }], stream: false }));
  else parts.push('### 输入限制', '该模型当前不接受图片输入；需要识图时选择 /v1/models 中 imageInput=true 的模型。');
  parts.push('### 返回结果', json({ id: 'chatcmpl_example', object: 'chat.completion', model: id, choices: [
    { index: 0, message: { role: 'assistant', content: '你好。' }, finish_reason: 'stop' },
  ], usage: { prompt_tokens: 8, completion_tokens: 3, total_tokens: 11 } }),
  '以上内容与用量为结构示例，不是价格或实际计费承诺。Responses 从 output 中读取文本；字段区别见[读取结果](text.md#读取结果)。');
  return parts.join('\n\n');
}

function imageGuide(model, refs) {
  const { id, capabilities: caps } = model;
  const gpt = id.startsWith('gpt-image');
  const overseas = id.startsWith('dola-');
  const n = gpt ? (id === 'gpt-image-2' ? 'MaxModel 渠道为 1，ModelTop 渠道最多 10' : '最多 10 张') : String(caps.maxN || 1);
  const body = { model: id, prompt: '白色背景上的蓝色陶瓷杯', n: 1 };
  if (gpt) Object.assign(body, { size: '1024x1024', response_format: 'b64_json' });
  else Object.assign(body, { response_format: 'url', ...(overseas ? { size: '2K' } : {}) });
  const rows = [modelField(id),
    [inline('prompt'), '是', '字符串，1～32000 个字符'],
    [inline('n'), '否', '整数；该模型数量限制：' + n],
    [inline('size'), '否', gpt ? '像素尺寸，例如 1024x1024；不能使用 1K/2K 简写' : overseas ? '支持 ' + caps.sizes.join('、') + '，默认 2K' : '按模型能力填写支持的尺寸等级或像素尺寸'],
    [inline('response_format'), '否', 'url 或 b64_json；默认 url，GPT 的 ModelTop 渠道优先读取 b64_json'],
  ];
  if (caps.imageInput) rows.push([inline('image'), '否', 'URL、Data URL 或数组；最多 ' + caps.maxInputImages + ' 张参考图']);
  if (gpt) rows.push([inline('quality'), '否', id === 'gpt-image-2' ? 'auto、low、medium、high，按渠道支持使用' : 'auto、low、medium、high、xhigh、max']);
  if (caps.sequentialImages) rows.push([inline('sequential_image_generation') + ' / ' + inline('sequential_image_generation_options'), '否', '组图参数，结果数量不得超过 maxN']);
  const parts = ['### 接口', inline('POST /v1/images/generations'),
    '请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。',
    '### 请求示例', curl('/v1/images/generations', body, { idempotency: true }),
    '### 请求参数', table(rows), '### 模型限制'];
  if (gpt) parts.push(
    '同名模型可能绑定不同渠道；不能在请求中选择渠道。当前 ModelTop 只开放文生图，不提供参考图编辑、流式或 -gp 异步生图。',
    id === 'gpt-image-2' ? 'MaxModel 当前单张；ModelTop 最多 10 张。读取当前 /v1/models 的 maxN 后再设置数量。' : '仅 2.5 系列支持透明背景、自定义尺寸、png/jpeg/webp 和输出压缩率。透明背景不能输出 JPEG。',
    section(refs.images, '### ModelTop 请求参数').replaceAll('"gpt-image-2"', '"' + id + '"'));
  else if (overseas) parts.push(
    '参考图单张 Data URL 解码后不超过 30 MiB。' + (caps.maxN > 1 ? '参考图与结果图合计不能超过 15。' : '每次只输出 1 张，不接受组图参数。'),
    'Pro/Flash 自定义尺寸总像素为 921,600～4,624,220；Lite 为 3,686,400～16,777,216，宽高比为 1/16～16。三款支持 png/jpeg，不接受 quality、style、background；Pro 的提示词优化额外支持 fast。',
    '完整型号差异见[海外 Seedream 参数](images.md#byteplus-seedream)。');
  else parts.push(
    '最多 ' + caps.maxInputImages + ' 张参考图，单张 Data URL 解码后不超过 10 MiB。结果数量上限为 ' + caps.maxN + '。',
    'quality、style、user 不向该模型转发；negative_prompt 不属于公开字段，负向要求应写入 prompt。其他选项仅在 /v1/models 的能力声明支持时使用。');
  if (caps.imageInput) parts.push('### 参考图示例', curl('/v1/images/generations', { ...body, image: 'https://customer.example.com/reference.jpg' }, { idempotency: true }));
  parts.push('### 返回结果', json({ created: 1792108800, model: id, data: [gpt ? { b64_json: 'BASE64_IMAGE_DATA' } : { url: 'https://provider.example.com/result.png' }] }),
    '结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。',
    '完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。');
  return parts.join('\n\n');
}

function videoGuide(model) {
  const { id, capabilities: caps } = model;
  const seedance = id.includes('seedance');
  const overseas = id.startsWith('dreamina');
  const mini = /fast|mini/.test(id);
  const path = '/api/v3/contents/generations/tasks';
  const body = { model: id, content: [{ type: 'text', text: '晨光下的海面，镜头缓慢推进' }],
    duration: seedance ? 4 : id.startsWith('wan') ? 8 : 6,
    resolution: seedance ? '480p' : id.startsWith('wan') ? '1080P' : '768P', ratio: '16:9' };
  const parts = ['### 接口', [inline('POST ' + path), inline('GET ' + path + '/{taskId}'), inline('DELETE ' + path + '/{taskId}')].join('\n\n'),
    '创建为异步操作。支持取消的渠道才能使用 DELETE；不支持时返回 video_cancel_unsupported。',
    '### 创建示例', curl(path, body, { idempotency: true }),
    '### 请求参数', table([modelField(id),
      [inline('content'), '是', '内容数组，包含文本及模型支持的参考素材'],
      [inline('duration'), '否', seedance ? caps.durationMin + '～' + caps.durationMax + ' 秒' + (caps.smartDuration ? '；支持 -1 智能时长' : '') : '模型支持的时长，按当前能力和返回校验结果设置'],
      [inline('resolution'), '否', seedance ? caps.resolutions.join('、') + (overseas && !mini && id.includes('2.0') ? '；ModelTop 渠道另支持 4k' : '') : id.startsWith('wan') ? '当前默认 1080P' : '当前默认 768P'],
      [inline('ratio'), '否', '画幅比例，例如 16:9；不使用 aspect_ratio'],
      [inline('generate_audio'), '否', id.startsWith('minimax') ? '不支持该字段' : '按模型能力决定是否接受，示例中省略'],
      [inline('watermark'), '否', '布尔值，按模型能力决定是否支持'],
    ]), '### 模型与素材限制'];
  if (overseas) parts.push(
    '图片最多 ' + caps.maxImages + ' 张，视频最多 ' + caps.maxVideos + ' 个，音频最多 ' + caps.maxAudios + ' 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。',
    'BytePlus 渠道不接受 seed、camera_fixed、frames、draft 或 service_tier=flex，且仅排队任务允许取消。ModelTop 渠道不开放取消与草稿；具体差异见[ModelTop 视频](videos.md#modeltop-视频)。',
    '素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。');
  else if (id.startsWith('wan')) parts.push('最多一张 HTTP(S) 首帧图片，role 必须为 first_frame。只支持 duration、resolution、ratio、generate_audio、watermark，不支持 seed 等额外参数。');
  else if (id.startsWith('minimax')) parts.push('只接受 HTTP(S) 图片，内容总计不超过 20 项。支持 duration、resolution、ratio、seed、watermark，不支持 generate_audio 与取消任务。');
  else parts.push('参考图片、视频、音频及特殊参数须符合该模型 /v1/models 的能力。图片角色为 first_frame、last_frame 或 reference_image，视频使用 reference_video，音频使用 reference_audio。');
  parts.push('### 创建响应', json({ id: 'vid_example' }),
    '### 查询结果', fence('bash', 'curl "$BASE_URL' + path + '/$TASK_ID" \\\n  -H "Authorization: Bearer $API_KEY"'),
    '必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。',
    '### 成功结果示例', json({ id: 'vid_example', model: id, status: 'succeeded', resolution: body.resolution, ratio: '16:9', duration: body.duration, content: { video_url: 'https://provider.example.com/result.mp4' } }),
    '若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。',
    '### 取消任务', fence('bash', 'curl -X DELETE "$BASE_URL' + path + '/$TASK_ID" \\\n  -H "Authorization: Bearer $API_KEY"'),
    '支持取消的渠道成功返回 204，无响应体；ModelTop、Wan 和 MiniMax 当前不支持取消。公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。');
  return parts.join('\n\n');
}

export function modelGuide(model, refs) {
  let body;
  if (model.modality === 'text') body = textGuide(model);
  else if (model.modality === 'image') body = imageGuide(model, refs);
  else if (model.modality === 'video') body = videoGuide(model);
  else if (model.modality === 'embedding') body = refs.embeddings.replace(/^# .+\n/, '').replace(/^\[文档首页\].+\n/m, '').replace(/^## /gm, '### ').replace('### 请求字段', '### 请求参数');
  else {
    const heading = model.capabilities.speech ? '## 语音合成' : model.capabilities.transcriptions ? '## 创建录音识别任务' : '## 音频生成';
    body = '### 接口与参数\n\n' + section(refs.audio, heading);
    if (model.capabilities.transcriptions) body += '\n\n### 查询结果\n\n' + section(refs.audio, '## 查询录音识别任务');
  }
  // Endpoint references put fields before examples, while task query/cancel flows keep their order.
  const parameters = body.match(/### 请求参数\n[\s\S]*?(?=\n### |$)/)?.[0];
  if (parameters && body.startsWith('### 接口\n')) {
    body = body.replace(parameters, '').replace(/\n{3,}/g, '\n\n');
    const nextSection = body.indexOf('\n### ', 1);
    if (nextSection > 0) body = body.slice(0, nextSection) + '\n\n' + parameters + body.slice(nextSection);
  }
  return [
    '## ' + inline(model.id), model.summary,
    '[鉴权](basics.md) · [错误与安全重试](errors.md)',
    '需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值。',
    body,
    '### 查询模型价格',
    fence('bash', 'curl "$BASE_URL/v1/pricing?model=' + model.id + '" \\\n  -H "Authorization: Bearer $API_KEY"'),
    '价格查询按名称包含匹配，请从 data 中选择 id 完全等于 ' + inline(model.id) + ' 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。',
  ].join('\n\n') + '\n';
}
