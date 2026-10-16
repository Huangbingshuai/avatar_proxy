// Public, request-relevant channel differences only. Contract tests compare
// these capabilities with the backend's effective per-channel catalogue.
export const supplierLabels = {
  volcengine_ark: '火山引擎', byteplus_modelark: 'BytePlus', maxmodel: 'MaxModel', modeltop: 'ModelTop',
  volcengine_speech: '豆包语音', aliyun_bailian: '阿里百炼', minimax: 'MiniMax',
};
export const supplierOrder = Object.keys(supplierLabels);
export const supplierPageId = model => 'model-' + model.id + (model.primary ? '' : '-' + model.provider);
export const supplierHeading = (alias, label) => alias + ' ' + label + ' 供应商';
export function primarySupplier(model) {
  if (model.id.startsWith('gpt-image-2.5') || model.id.endsWith('-filter-off')) return 'modeltop';
  if (model.id === 'gpt-image-2') return 'maxmodel';
  if (model.id.startsWith('dreamina-') || model.id.startsWith('dola-')) return 'byteplus_modelark';
  if (model.id.startsWith('wan')) return 'aliyun_bailian';
  if (model.id.startsWith('minimax')) return 'minimax';
  if (model.modality === 'audio') return 'volcengine_speech';
  return 'volcengine_ark';
}
export function supplierModels(model) {
  let variants;
  if (model.id === 'gpt-image-2') return [
    { ...model, summary: '同步文生图；单次 1 张结果', primary: true, provider: 'maxmodel', supplierLabel: 'MaxModel' },
    { ...model, summary: '同步文生图；最多 10 张，原生返回 Base64', primary: false, provider: 'modeltop', supplierLabel: 'ModelTop', capabilities: {
      generations: true, maxN: 10, billingMetric: 'image_tokens', billingUnit: 1000000,
      imageTokenBilling: true, qualityLevels: ['auto', 'low', 'medium', 'high'],
      customSizes: false, outputFormat: false,
    } },
  ];
  if (/^dreamina-seedance-2\.(5|0)(-fast|-mini)?$/.test(model.id)) variants = [
    { ...model, primary: true, provider: 'byteplus_modelark', supplierLabel: 'BytePlus' },
    { ...model, primary: false, provider: 'modeltop', supplierLabel: 'ModelTop', capabilities: {
      ...model.capabilities, seed: true, returnLastFrame: true, cancelSupported: false,
      resolutions: model.id === 'dreamina-seedance-2.0' ? [...model.capabilities.resolutions, '4k'] : model.capabilities.resolutions,
      // This adapter doesn't accept output_format, including on 2.5.
      outputFormats: undefined,
    } },
  ];
  if (variants) return variants;
  const provider = primarySupplier(model);
  return [{ ...model, primary: true, provider, supplierLabel: supplierLabels[provider] }];
}
