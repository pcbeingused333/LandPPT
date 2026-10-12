import { useEffect, useRef, useState, type FocusEvent } from 'react';
import { AutoComplete, Input, Select } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import type { Field } from '../settings-schema';

export function ModelPicker({ field, value, options, fetched, disabled, change }: {
  field: Field; value: string; options: Field['options']; fetched?: Field['options'];
  disabled: boolean; change: (name: string, value: unknown) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const previous = useRef(fetched);
  const reveal = useRef(false);
  const id = `field-${field.name}`;
  useEffect(() => {
    if (previous.current !== fetched) { previous.current = fetched; reveal.current = !!fetched; }
    if (!reveal.current || disabled) return;
    reveal.current = false; setQuery('');
    const input = document.getElementById(id);
    // Do not move focus into a tab that the user has left during the request.
    if (input?.getClientRects().length) { input.focus(); setOpen(options.length > 0); }
    else setOpen(false);
  }, [fetched, disabled, id, options.length]);
  const common = { id, 'aria-label': field.label, placeholder: field.placeholder, disabled, value, options,
    open: open && !disabled, onOpenChange: setOpen,
    onChange: (next: string) => change(field.name, next),
    onFocus: (event: FocusEvent<HTMLElement>) => { if (event.target.id === id) { setQuery(''); setOpen(true); } },
    onBlur: () => { setOpen(false); setQuery(''); },
    onSelect: () => { setOpen(false); setQuery(''); },
  };
  if (field.kind === 'select') return <Select {...common} showSearch optionFilterProp="label" />;
  return <AutoComplete {...common} classNames={{ popup: { root: 'settings-model-popup' } }} showSearch={{
    onSearch: next => { setQuery(next); setOpen(true); },
    // The saved value is not a search query when the list is opened.
    filterOption: (_input, option) => !query || String(option?.value).toLowerCase().includes(query.toLowerCase()),
  }}><Input name={field.name} className="settings-model-input" suffix={<button type="button" className="settings-model-toggle" disabled={disabled || !options.length}
    aria-label={`展开${field.label}列表`} aria-haspopup="listbox" aria-controls={`${id}_list`} aria-expanded={open && !disabled && !!options.length}
    onMouseDown={event => { event.preventDefault(); event.stopPropagation(); }} onClick={event => { event.stopPropagation(); setQuery(''); document.getElementById(id)?.focus(); setOpen(true); }}><DownOutlined aria-hidden /></button>} /></AutoComplete>;
}
