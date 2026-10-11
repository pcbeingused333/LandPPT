import { useEffect, useState } from 'react';
import { Alert, Button, Descriptions, Form, Input, Modal, Select, Space, Spin } from 'antd';
import { request, type ApiData } from '../api';
import { useAdminActions } from '../components/admin-data';
import { ImageActions, ImagePreview, fileSize, imageEndpoint, imageSources, sourceLabel } from '../components/images';
import { modalFocus } from '../components/modal-focus';
import { formatTime } from '../forms';

export default function ImageDetail({ id, onClose, onSaved, onDelete }: { id?: string; onClose: () => void; onSaved: () => Promise<void>; onDelete: (id: string) => void }) {
  const [image, setImage] = useState<ApiData>(); const [editing, setEditing] = useState(false); const [loading, setLoading] = useState(false); const [error, setError] = useState(''); const [retry, setRetry] = useState(0);
  const [form] = Form.useForm(); const actions = useAdminActions();
  useEffect(() => {
    setImage(undefined); setEditing(false); setError(''); actions.clearError(); if (!id) return;
    const controller = new AbortController(); setLoading(true);
    request(imageEndpoint('detail', id), 'GET', undefined, controller.signal).then(data => {
      if (!controller.signal.aborted) { if (!data.image) throw new Error('图片详情为空'); setImage(data.image); }
    }).catch(reason => { if (!controller.signal.aborted) setError(reason.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id, retry]);
  async function save() {
    if (!id || !image) return;
    const values = form.getFieldsValue();
    try {
      const result = await actions.run(`/api/image/${encodeURIComponent(id)}/update`, 'PUT', { title: String(values.title || '').trim(), description: String(values.description || '').trim(), tags: String(values.tags || '').trim(), category: values.category || image.category });
      setImage({ ...image, ...result.image }); setEditing(false); actions.message.success('图片信息已更新'); await onSaved();
    } catch { /* Keep the user's draft. */ }
  }
  return <Modal centered open={!!id} width={820} title={editing ? '编辑图片信息' : '图片详情'} modalRender={modalFocus} closable={!actions.pending} mask={{ closable: !actions.pending }} keyboard={!actions.pending} onCancel={onClose} footer={editing ? <Space><Button disabled={actions.pending} onClick={() => { setEditing(false); actions.clearError(); }}>取消编辑</Button><Button type="primary" loading={actions.pending} onClick={save}>保存信息</Button></Space> : <Space wrap>
    <Button onClick={onClose}>关闭</Button>{image && <><Button danger disabled={actions.pending} onClick={() => onDelete(id!)}>删除图片</Button><Button type="primary" onClick={() => { actions.clearError(); form.setFieldsValue(image); setEditing(true); }}>编辑信息</Button></>}
  </Space>}>
    {loading && <div role="status" className="image-loading"><Spin /> 正在加载详情…</div>}
    {error && <Alert type="error" title="详情加载失败" description={error} action={<Button onClick={() => setRetry(value => value + 1)}>重试</Button>} />}
    {image && <div className="image-detail-grid"><div><ImagePreview src={imageEndpoint('view', id!)} title={image.title || image.filename} /><ImageActions url={imageEndpoint('view', id!)} downloadURL={imageEndpoint('download', id!)} disabled={actions.pending} /></div>
      <div>{editing ? <Form form={form} layout="vertical" disabled={actions.pending}>
        <Form.Item name="title" label="标题"><Input /></Form.Item><Form.Item name="description" label="描述"><Input.TextArea rows={3} /></Form.Item>
        <Form.Item name="tags" label="标签"><Input placeholder="用逗号分隔" /></Form.Item><Form.Item name="category" label="来源分类"><Select options={imageSources} /></Form.Item>
      </Form> : <Descriptions column={1} size="small" items={[['标题', image.title], ['描述', image.description], ['标签', image.tags], ['来源', sourceLabel(image.category || image.source_type)], ['文件', image.filename], ['大小', fileSize(image.file_size)], ['尺寸', `${image.width} × ${image.height}`], ['格式', String(image.format || '').toUpperCase()], ['创建时间', formatTime(image.created_at)], ['访问次数', String(image.access_count || 0)]].map(([label, children]) => ({ key: label, label, children: children || '—' }))} />}
        {actions.error && <Alert type="error" title={actions.error} />}
      </div>
    </div>}
  </Modal>;
}
