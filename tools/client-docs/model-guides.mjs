const tick = String.fromCharCode(96);
const inline = value => tick + value + tick;
const fence = (language, body) => tick.repeat(3) + language + '\n' + body + '\n' + tick.repeat(3);
const json = body => fence('json', JSON.stringify(body, null, 2));
const table = rows => ['| 参数 | 必填 | 类型与说明 |', '|---|---|---|', ...rows.map(row => '| ' + row.join(' | ') + ' |')].join('\n');
export const modelPageId = alias => 'model-' + alias;
export function modelFamily(model) {
  if (model.id.startsWith('vega-') || model.id.startsWith('wand-vega-vl-')) return 'Vega';
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
  if (id.startsWith('wand-vega-vl-')) return [
    '### 接口', inline('POST /v1/chat/completions'),
    'Vega渠道的多模态理解模型，仅支持Chat Completions JSON和SSE；不支持Responses。' + (caps.textOnly ? '可输入纯文本或多模态内容。' : 'Pro必须输入至少一种图片、音频、视频或文件，不能只传纯文本。'),
    '### 请求示例', curl('/v1/chat/completions', { model: id, messages: [{ role: 'user', content: [
      { type: 'text', text: '请描述这个视频的内容' }, { type: 'video_url', video_url: { url: 'https://customer.example.com/video.mp4' } },
    ] }], stream: false, thinking_enabled: true }),
    '### 请求参数', table([modelField(id), [inline('messages'), '是', '消息数组，role支持system、developer、user、assistant、tool'],
      [inline('stream'), '否', '布尔值，省略按false；true返回SSE'],
      [inline('thinking_enabled'), '否', '布尔值，是否开启思考'],
      [inline('reasoning_effort'), '否', 'none/minimal/low/medium/high/xhigh；同时设置时优先于thinking_enabled'],
      [inline('reasoning_split'), '否', '布尔值，是否分离思考与正文'],
      [inline('temperature'), '否', '数字0～2'],
      [inline('max_tokens') + ' / ' + inline('max_completion_tokens'), '否', '正整数，按供应商文档包含输入和输出；同时设置时max_tokens优先'],
      [inline('tools') + ' / ' + inline('tool_choice') + ' / ' + inline('response_format'), '否', 'OpenAI工具和结构化输出参数'],
    ]),
    '### 多模态输入',
    'Part支持text、image_url、video_url、input_audio、file。音频使用input_audio.url，或data（裸Base64）+format（mp3/wav）；文件使用file.file_url，或file.file_data（Data URL）+file.file_name。不要把file_url放在Part顶层。视频每次最多10个；内联文件上限100 MiB，远程大小由供应商校验。',
    '### 流式调用', curl('/v1/chat/completions', { model: id, messages: [{ role: 'user', content: [
      { type: 'text', text: '请描述图片' }, { type: 'image_url', image_url: { url: 'https://customer.example.com/image.jpg' } },
    ] }], stream: true }, { stream: true }),
    '逐行读取choices[].delta；reasoning_content/reasoning_details原样保留。可选请求头Tx-User-Session-Id用于同一会话缓存，服务端会先按当前项目及业务Key隔离后再传给供应商。',
    '### 返回结果', json({ model: id, choices: [{ message: { role: 'assistant', content: '视频中是一片湖泊。' } }],
      usage: { prompt_tokens: 100, prompt_tokens_details: { cached_tokens: 30, video_tokens: 60 }, completion_tokens: 20, total_tokens: 120 } }),
    '仅使用真实Token计费；缓存Token从普通输入中扣除后按缓存价计算，不重复收费。video_tokens和reasoning_tokens属于输入/输出明细，不额外叠加。用量缺失进入待核对。详见[Vega生图与理解](vega-image-vl.md)。',
  ].join('\n\n');
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

function imageGuide(model) {
  const { id, capabilities: caps } = model;
  if (id.startsWith('vega-image-')) return [
    '### 接口', inline('POST /v1/images/tasks'),
    'Vega异步生图。提交后保存本站返回的id，使用相同业务Key轮询；必须发送Idempotency-Key。',
    '### 请求示例', curl('/v1/images/tasks', { model: id, prompt: '白色背景上的蓝色陶瓷杯', size: '2K', aspect_ratio: '16:9', n: 1 }, { idempotency: true }),
    '### 请求参数', table([modelField(id), [inline('prompt'), '有条件', '最多2000字符；没有参考图时必填'],
      [inline('image'), '否', 'HTTP(S) URL、图片Data URL或数组；最多' + caps.maxInputImages + '张'],
      [inline('size'), '否', '1K、2K、4K或文档像素预设，默认1K'], [inline('aspect_ratio'), '否', '1:1、2:3、3:2、3:4、4:3、9:16、16:9、21:9，默认1:1'],
      [inline('n'), '否', 'Lite仅1；Flash/Pro系统上限15，最终受供应商限制'],
      [inline('response_format'), '否', '仅url，结果为临时地址'], [inline('watermark'), '否', '布尔值，映射供应商的图标水印选项'],
    ]),
    '### 查询任务', fence('bash', 'curl "$BASE_URL/v1/images/tasks/$TASK_ID" \\\n  -H "Authorization: Bearer $API_KEY"'),
    '### 返回结果', json({ id: 'img_xxx', object: 'image_task', model: id, status: 'succeeded', progress: 100,
      result: { model: id, task_id: 'img_xxx', data: [{ url: 'https://provider.example.com/result.png', expires_at: '2026-12-01T00:00:00Z' }] } }),
    'status为queued/running/succeeded/failed；完成后读取result.data[].url。不能使用其他Key读取任务。凭证轮换和渠道停用后，既有任务仍固定原凭证查询。',
    '### 同步兼容接口', curl('/v1/images/generations', { model: id, prompt: '白色背景上的蓝色陶瓷杯', size: '1K' }, { idempotency: true }),
    '同步兼容接口会等待同一异步任务完成，并返回OpenAI图片结构。长任务推荐直接使用异步接口；超时保留taskId，查询原任务，勿更换幂等键重复生成。',
    '### 素材和计费', '支持JPEG、PNG、WebP Data URL；服务端去掉前缀后传供应商，所有内联图合计不超过7 MiB。远程参考图按供应商最终格式和大小限制校验。像素预设映射分辨率和比例，实际尺寸以返回结果为准。',
    'Lite、Flash输入免费；Pro前三张输入免费，第四张起计费。输出按实际返回张数，不按请求n估算；国际站生图价格未提供，需管理员配置后计价。临时地址可能过期，请及时下载。',
    '完整流程见[Vega生图与理解](vega-image-vl.md)。',
  ].join('\n\n');
  const gpt = id.startsWith('gpt-image');
  const overseas = id.startsWith('dola-');
  const modeltop = model.provider === 'modeltop' || id.startsWith('gpt-image-2.5');
  const n = String(caps.maxN || 1);
  const body = { model: id, prompt: '白色背景上的蓝色陶瓷杯', n: 1 };
  if (gpt) Object.assign(body, { size: '1024x1024', response_format: modeltop ? 'b64_json' : 'url' });
  else Object.assign(body, { response_format: 'url', size: '2K' });
  const rows = [modelField(id),
    [inline('prompt'), '是', '字符串，1～32000 个字符'],
    [inline('n'), '否', '整数；该模型数量限制：' + n],
    [inline('size'), '否', gpt ? '像素尺寸，例如 1024x1024；不能使用 1K/2K 简写' : overseas ? '支持 ' + caps.sizes.join('、') + '，默认 2K' : '本页示例使用 2K；其他尺寸等级或像素尺寸须符合该型号限制'],
    [inline('response_format'), '否', modeltop ? 'url 或 b64_json；原生返回 Base64，此参数不传往上游，按 data[].b64_json 读取' : 'url 或 b64_json；默认 url'],
  ];
  if (caps.imageInput) rows.push([inline('image'), '否', 'URL、Data URL 或数组；最多 ' + caps.maxInputImages + ' 张参考图']);
  if (modeltop) rows.push([inline('quality'), '否', caps.qualityLevels.join('、') + '；默认 auto']);
  if (caps.sequentialImages) rows.push([inline('sequential_image_generation') + ' / ' + inline('sequential_image_generation_options'), '否', '组图参数，结果数量不得超过 maxN']);
  const parts = ['### 接口', inline('POST /v1/images/generations'),
    '请求和响应均为 JSON；当前不支持流式图片输出。建议提前保存 Idempotency-Key 和原请求体。',
    '### 请求示例', curl('/v1/images/generations', body, { idempotency: true }),
    '### 请求参数', table(rows), '### 模型限制'];
  if (modeltop) parts.push(
    '当前只开放文生图，不提供参考图编辑、流式或 -gp 异步生图。',
    id === 'gpt-image-2' ? '最多 10 张，不支持自定义尺寸、透明背景或显式 output_format/output_compression。可选背景仅 auto、opaque。' : '支持透明背景、自定义尺寸、png/jpeg/webp 和输出压缩率。透明背景不能输出 JPEG。',
    'size 可选 auto、1024x1024、1536x1024、1024x1536、2048x2048、2048x1152、3840x2160、2160x3840。不能使用 1K/2K 简写。',
    ...(caps.customSizes ? ['自定义尺寸边长≤3840，均为16的倍数，宽高比≤3:1，总像素655360～8294400。background 为 auto/opaque/transparent；output_format 为 png/jpeg/webp；仅 JPEG/WebP 可设置整数 output_compression=0..100。'] : []),
    '不接受 image、watermark、style、seed、tools、moderation 等其他渠道字段。原生返回 Base64，响应中的 usage 保留实际细分 Token，不按固定张价推算。');
  else if (gpt) parts.push('当前单次只能生成 1 张；不要套用其他渠道的多图、自定义尺寸、透明背景或图片 Token 能力。示例仅使用当前已接入的同步文生图字段。其他兼容选项由服务校验，不作为本页可用能力承诺。');
  else if (overseas) parts.push(
    '参考图单张 Data URL 解码后不超过 30 MiB。' + (caps.maxN > 1 ? '参考图与结果图合计不能超过 15。' : '每次只输出 1 张，不接受组图参数。'),
    'Pro/Flash 自定义尺寸总像素为 921,600～4,624,220；Lite 为 3,686,400～16,777,216，宽高比为 1/16～16。三款支持 png/jpeg，不接受 quality、style、background；Pro 的提示词优化额外支持 fast。',
    '完整型号差异见[海外 Seedream 参数](images.md#byteplus-seedream)。');
  else parts.push(
    '最多 ' + caps.maxInputImages + ' 张参考图，单张 Data URL 解码后不超过 10 MiB。结果数量上限为 ' + caps.maxN + '。',
    'quality、style、user 不向该模型转发；negative_prompt 不属于公开字段，负向要求应写入 prompt。其他选项仅在 /v1/models 的能力声明支持时使用。');
  if (caps.imageInput) parts.push('### 参考图示例', curl('/v1/images/generations', { ...body, image: 'https://customer.example.com/reference.jpg' }, { idempotency: true }));
  parts.push('### 返回结果', json({ created: 1792108800, model: id, data: [modeltop ? { b64_json: 'BASE64_IMAGE_DATA' } : { url: 'https://provider.example.com/result.png' }] }),
    '结果 URL 可能过期，请及时下载。usage 仅包含真实返回值；未返回用量不代表免费。',
    '完整可选字段见[图片参数速查](images.md#请求字段速查)。断线后使用同一 Key、同一幂等键及原始请求恢复，不要换键重发。');
  return parts.join('\n\n');
}

function vegaGuide({ id, capabilities: caps }) {
  const path = '/api/v3/contents/generations/tasks';
  const body = { model: id, content: [{ type: 'text', text: '晨光下的海面，镜头缓慢推进' }], duration: 4,
    resolution: caps.defaultResolution, ratio: '16:9', generate_audio: true };
  return [
    '### 接口', inline('POST ' + path) + '\n\n' + inline('GET ' + path + '/{taskId}'),
    '异步生成，不支持取消。仅使用星辰平台业务 Key，无需传入腾讯云凭证、SubAppId 或 ModelVersion。',
    '### 请求参数', table([modelField(id),
      [inline('content'), '是', '文本、图片、视频、音频数组，格式见下方说明'],
      [inline('duration'), '否', '4～' + caps.durationMax + '秒，支持小数；默认4秒' + (caps.smartDuration ? '，-1表示智能时长' : '，不支持-1')],
      [inline('resolution'), '否', caps.resolutions.join('、') + '；默认' + caps.defaultResolution],
      [inline('ratio'), '否', '21:9、16:9、4:3、1:1、3:4、9:16、adaptive；默认16:9'],
      [inline('generate_audio'), '否', '布尔值，默认true'],
      [inline('vega'), '否', '模型专用选项对象，见[Vega参数与素材流程](vega.md)'],
      ...(caps.seed ? [[inline('seed'), '否', '整数-1～2147483647'], [inline('return_last_frame'), '否', '布尔值；通过content.last_frame_url读取'],
        [inline('output_format'), '否', 'mp4或mov']] : []),
    ]),
    '### 创建示例', curl(path, body, { idempotency: true }),
    '### 素材与生成限制',
    '图片最多' + caps.maxImages + '张，视频最多' + caps.maxVideos + '段，音频最多' + caps.maxAudios + '段，合计最多' + caps.maxFiles + '个文件。图片role为first_frame、last_frame或reference_image；视频为reference_video；音频为reference_audio。首尾帧各最多一张，不能与全模态参考混用；音频必须搭配图片或视频。只接受HTTP(S) URL或同Key同渠道登记的asset://素材，不接受Data URL。',
    id === 'vega-1.0-lite' ? 'Lite提示词最多7000字符，默认开启提示词优化，支持单独尾帧。' : 'Pro默认关闭提示词优化；真人素材须先完成[Vega素材注册流程](vega.md#素材与真人活体流程)。',
    '不支持frames、watermark、camera_fixed、draft、task_type、service_tier、execution_expires_after等其他渠道参数。任务类型使用vega.task_type，而非顶层task_type。远程媒体格式、时长、分辨率与大小由供应商最终校验；详细限制见[Vega接口](vega.md)。',
    '### 创建响应', json({ id: 'vid_example' }),
    '### 查询结果', fence('bash', 'curl "$BASE_URL' + path + '/$TASK_ID" \\\n  -H "Authorization: Bearer $API_KEY"'),
    '使用创建任务的同一枚业务Key，每5～10秒轮询；queued/running为未完成，succeeded/failed为终态。供应商默认通常只有1路并发，429时不要自动换幂等键重提。',
    '### 成功结果示例', json({ id: 'vid_example', model: id, status: 'succeeded', duration: 4,
      content: { video_url: 'https://provider.example.com/result.mp4' }, usage: { vega: { InputSeconds: 0, OutputSeconds: 4 } } }),
    'usage.vega为腾讯云真实计费用量；若返回completion_tokens/total_tokens则为真实Token，不代替按秒计费。未知用量不按零计算。结果采用供应商临时存储，URL可能过期，请及时下载；本站不另存TOS。',
  ].join('\n\n');
}

function videoGuide(model) {
  const { id, capabilities: caps } = model;
  if (id.startsWith('vega-')) return vegaGuide(model);
  const seedance = id.includes('seedance');
  const overseas = id.startsWith('dreamina');
  const modeltop = model.provider === 'modeltop' || id.endsWith('-filter-off');
  const cancellable = caps.cancelSupported !== false && seedance;
  const path = '/api/v3/contents/generations/tasks';
  const body = { model: id, content: [{ type: 'text', text: '晨光下的海面，镜头缓慢推进' }],
    duration: seedance ? 4 : id.startsWith('wan') ? 8 : 6,
    resolution: seedance ? '480p' : id.startsWith('wan') ? '1080P' : '768P', ratio: '16:9' };
  const parts = ['### 接口', [inline('POST ' + path), inline('GET ' + path + '/{taskId}'), ...(cancellable ? [inline('DELETE ' + path + '/{taskId}')] : [])].join('\n\n'),
    '创建为异步操作。' + (cancellable ? '支持取消；排队任务可取消，运行中任务可能被拒绝。' : '当前模型渠道不支持取消任务；调用 DELETE 会返回 422 video_cancel_unsupported。'),
    '### 创建示例', curl(path, body, { idempotency: true }),
    '### 请求参数', table([modelField(id),
      [inline('content'), '是', '内容数组，包含文本及模型支持的参考素材'],
      [inline('duration'), '否', seedance ? caps.durationMin + '～' + caps.durationMax + ' 秒' + (caps.smartDuration ? '；支持 -1 智能时长' : '') : '模型支持的时长，按当前能力和返回校验结果设置'],
      [inline('resolution'), '否', seedance ? caps.resolutions.join('、') : id.startsWith('wan') ? '当前默认 1080P' : '当前默认 768P'],
      [inline('ratio'), '否', '画幅比例，例如 16:9；不使用 aspect_ratio'],
      [inline('generate_audio'), '否', id.startsWith('minimax') ? '不支持该字段' : '按模型能力决定是否接受，示例中省略'],
      [inline('watermark'), '否', '布尔值，按模型能力决定是否支持'],
      ...(overseas && caps.seed ? [[inline('seed'), '否', '随机种子；当前渠道接受，具体范围由服务端校验']] : []),
      ...(overseas && caps.returnLastFrame ? [[inline('return_last_frame'), '否', '布尔值；true 请求返回末帧，结果从 content.last_frame_url 读取']] : []),
      ...(overseas ? [[inline('service_tier'), '否', '仅 default'], [inline('execution_expires_after'), '否', '3600～259200 的整数秒'], [inline('task_type'), '否', 't2v 或 i2v']] : []),
      ...(caps.outputFormats ? [[inline('output_format'), '否', caps.outputFormats.join('、')]] : []),
    ]), '### 模型与素材限制'];
  if (seedance) parts.push('ratio 仅允许 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；duration 必须为整数，不能与 frames 同时设置。execution_expires_after 为 3600～259200 的整数秒。其他可选参数见[视频参数](videos.md#参数与轮询注意事项)。');
  if (overseas) parts.push(
    '图片最多 ' + caps.maxImages + ' 张，视频最多 ' + caps.maxVideos + ' 个，音频最多 ' + caps.maxAudios + ' 段。首末帧不能与全能参考混用；2.0 系列音频需搭配图片或视频。',
    modeltop ? '接受 seed 和 return_last_frame；不接受 camera_fixed、frames、draft、output_format 或 service_tier=flex，不开放取消、回调或联网工具。' : '不接受 seed、camera_fixed、frames、draft 或 service_tier=flex。' + (caps.returnLastFrame ? '支持 return_last_frame。' : '不支持 return_last_frame=true。'),
    '素材 ID 不能保证跨渠道复用，优先使用目标模型可访问的 HTTP(S) URL 或允许的 Data URL。');
  else if (id.startsWith('wan')) parts.push('最多一张 HTTP(S) 首帧图片，role 必须为 first_frame。只支持 duration、resolution、ratio、generate_audio、watermark，不支持 seed 等额外参数。');
  else if (id.startsWith('minimax')) parts.push('只接受 HTTP(S) 图片，内容总计不超过 20 项。支持 duration、resolution、ratio、seed、watermark，不支持 generate_audio 与取消任务。');
  else parts.push('参考图片、视频、音频及特殊参数须符合该模型 /v1/models 的能力。图片角色为 first_frame、last_frame 或 reference_image，视频使用 reference_video，音频使用 reference_audio。');
  parts.push('### 创建响应', json({ id: 'vid_example' }),
    '### 查询结果', fence('bash', 'curl "$BASE_URL' + path + '/$TASK_ID" \\\n  -H "Authorization: Bearer $API_KEY"'),
    '必须使用创建任务的同一枚业务 Key，每 5～10 秒查询一次。queued / running 未完成，succeeded / failed / cancelled 为终态。',
    '### 成功结果示例', json({ id: 'vid_example', model: id, status: 'succeeded', resolution: body.resolution, ratio: '16:9', duration: body.duration, content: { video_url: 'https://provider.example.com/result.mp4' } }),
    '若返回 usage.completion_tokens，则是上游真实输出 Token；未返回时不能估算为零。计价指标和维度以 /v1/pricing 为准。结果链接可能过期，应及时保存。resolution、ratio、duration 等维度仅在响应中提供时出现，尤其 Wan 不保证返回全部维度。');
  if (cancellable) parts.push('### 取消任务', fence('bash', 'curl -X DELETE "$BASE_URL' + path + '/$TASK_ID" \\\n  -H "Authorization: Bearer $API_KEY"'),
    '仅在项目绑定渠道支持取消时执行。成功返回 204，无响应体。');
  parts.push('公共可选参数及渠道限制见[视频参考](videos.md#渠道与模型参数)。');
  return parts.join('\n\n');
}

export function modelGuide(model, refs) {
  let body;
  if (model.modality === 'text') body = textGuide(model);
  else if (model.modality === 'image') body = imageGuide(model);
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
    '需要该模型请联系管理员为项目开通。以下示例会产生真实用量；当前是否可用及能力以 /v1/models 为准。先按[示例约定](basics.md#地址与示例约定)设置 BASE_URL 和 API_KEY。示例幂等键须替换为本次操作的唯一业务 ID，断线恢复时保持原值；媒体 URL 和任务 ID 须替换为自己的真实值。',
    body,
    '### 查询模型价格',
    fence('bash', 'curl "$BASE_URL/v1/pricing?model=' + model.id + '" \\\n  -H "Authorization: Bearer $API_KEY"'),
    '价格查询按名称包含匹配，请从 data 中选择 id 完全等于 ' + inline(model.id) + ' 的项目。金额为人民币十进制字符串，未配置价格和未知用量不代表免费。',
  ].join('\n\n') + '\n';
}
