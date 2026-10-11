// Reuse the server-rendered field catalogue during page-by-page migration.
// The template stays inert: styles, scripts and inline handlers never execute.
export interface Field {
  name: string; kind: string; label: string; help: string; placeholder: string;
  value: string | boolean; min?: number; max?: number; step?: number; required: boolean;
  section: string; dependencies: string[]; options: { label: string; value: string }[];
  slider?: { min: number; max: number; step: number };
}
export interface Panel { key: string; label: string; fields: Field[] }
const clean = (node?: Element | null) => node?.textContent?.replace(/\s+/g, ' ').trim() || '';
const conditionIds: Record<string, string> = {
  'parallel-generation-options': 'enable_parallel_generation',
  'image-service-options': 'enable_image_service',
  'local-images-config': 'enable_local_images',
  'network-search-config': 'enable_network_search',
  'ai-generation-config': 'enable_ai_generation',
};

export function readSettingsSchema(): Panel[] {
  const source = document.querySelector<HTMLTemplateElement>('#settingsBlueprint')!.content;
  return Array.from(source.querySelectorAll<HTMLButtonElement>('.config-tabs [data-tab]')).map(tab => {
    const key = tab.dataset.tab!;
    const panel = source.getElementById(key)!;
    const fields = Array.from(panel.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>('input[name]:not([type=radio]):not([type=range]),select[name],textarea[name]')).map(input => {
      const group = input.closest('.form-group,.param-card,.parallel-showcase,.toggle-row,.toggle-label,.image-source-option') || input.parentElement!;
      const label = group.querySelector('.toggle-row-title,.param-card-label,.parallel-showcase-label') || (group.tagName === 'LABEL' ? group : group.querySelector('label'));
      const copy = label?.cloneNode(true) as Element | undefined;
      copy?.querySelectorAll('small,p,input,select,textarea,.param-card-label-code,.settings-field-code,button').forEach(node => node.remove());
      const provider = input.closest('[data-provider]')?.getAttribute('data-provider');
      const role = input.closest('tr[data-role-model-field]');
      const section = input.closest('.config-section,.settings-group,.settings-section');
      const title = section?.querySelector('h4')?.cloneNode(true) as Element | undefined;
      title?.querySelectorAll('small').forEach(node => node.remove());
      const subsection = input.closest('.sub-section,.settings-subsection');
      const subtitle = subsection?.querySelector('h5')?.cloneNode(true) as Element | undefined;
      subtitle?.querySelectorAll('small').forEach(node => node.remove());
      let labelText = clean(copy) || input.getAttribute('aria-label') || input.name;
      if (role) labelText = `${clean(role.querySelector('td'))}${input.name.endsWith('_provider') ? '提供者' : '模型'}`;
      const dependencies: string[] = [];
      let parent = input.parentElement;
      while (parent && parent !== panel) {
        if (conditionIds[parent.id]) dependencies.push(conditionIds[parent.id]);
        parent = parent.parentElement;
      }
      const options = Array.from(new Map(Array.from((input instanceof HTMLSelectElement ? input : group).querySelectorAll('option')).map(option => [option.value, { label: clean(option) || option.value, value: option.value }])).values());
      const range = group.querySelector<HTMLInputElement>('input[type=range]');
      const numeric = (name: string) => input.hasAttribute(name) ? Number(input.getAttribute(name)) : undefined;
      return {
        name: input.name, kind: input instanceof HTMLSelectElement ? 'select' : input instanceof HTMLTextAreaElement ? 'textarea' : input.type,
        label: labelText, help: clean(group.querySelector('small,.param-card-help,.toggle-row-desc,.field-help')),
        placeholder: input.getAttribute('placeholder') || '',
        value: input instanceof HTMLInputElement && input.type === 'checkbox' ? input.checked : input.value,
        min: numeric('min'), max: numeric('max'), step: numeric('step'), required: input.required,
        section: provider || (role ? '模型任务配置' : [clean(title), clean(subtitle)].filter(Boolean).join(' · ') || '基础设置'), dependencies, options,
        ...(range ? { slider: { min: Number(range.min), max: Number(range.max), step: Number(range.step) || 1 } } : {}),
      } as Field;
    });
    return { key, label: clean(tab), fields };
  });
}
