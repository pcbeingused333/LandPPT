import { useRef, useState } from 'react';
import { Alert, App, Form, Input, Modal, Progress, Select, Upload, type UploadFile } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import { errorText, type ApiData } from '../api';
import { modalFocus } from '../components/modal-focus';
import { uploadCategories } from '../components/images';

export default function ImageUpload({ open, onClose, onUploaded }: { open: boolean; onClose: () => void; onUploaded: () => Promise<void> }) {
  const { message } = App.useApp(); const [form] = Form.useForm(); const [files, setFiles] = useState<UploadFile[]>([]);
  const [pending, setPending] = useState(false); const [completed, setCompleted] = useState(0); const [errors, setErrors] = useState<string[]>([]); const lock = useRef(false);
  function close() { if (lock.current) return; setFiles([]); setErrors([]); setCompleted(0); form.resetFields(); onClose(); }
  async function upload() {
    if (lock.current || !files.length) return;
    const values = form.getFieldsValue(); lock.current = true; setPending(true); setErrors([]); setCompleted(0);
    const failed: UploadFile[] = []; const problems: string[] = []; let successes = 0;
    for (const [index, entry] of files.entries()) {
      const file = entry.originFileObj || entry as unknown as File; const body = new FormData(); body.append('file', file);
      const fields: ApiData = { title: String(values.title || '').trim() || file.name.split('.')[0], description: String(values.description || '').trim(), tags: String(values.tags || '').trim(), category: values.category || 'business' };
      for (const [key, value] of Object.entries(fields)) body.append(key, value);
      try {
        const response = await fetch('/api/image/upload', { method: 'POST', credentials: 'same-origin', body });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || result.success !== true) throw new Error(errorText(result.detail || result.message || '上传失败'));
        successes++;
      } catch (reason) { failed.push(entry); problems.push(`${file.name}：${(reason as Error).message}`); }
      setCompleted(index + 1);
    }
    lock.current = false; setPending(false); setErrors(problems); setFiles(failed);
    if (successes) { message.success(`成功上传 ${successes} 张图片`); await onUploaded(); }
    if (!failed.length) close();
  }
  return <Modal centered open={open} title="上传图片" width={560} okText={errors.length ? '重试未完成文件' : '开始上传'} cancelText="取消" confirmLoading={pending} okButtonProps={{ disabled: !files.length }} closable={!pending} mask={{ closable: !pending }} keyboard={!pending} onCancel={close} onOk={upload} modalRender={modalFocus}>
    <Form form={form} layout="vertical" initialValues={{ category: 'business' }} disabled={pending}>
      <Upload.Dragger accept="image/jpeg,image/png,image/webp,image/gif" multiple disabled={pending} fileList={files} beforeUpload={file => {
        if (!['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'].includes(file.type)) { message.error(`${file.name}：请选择 JPG、PNG、WebP 或 GIF 图片`); return Upload.LIST_IGNORE; }
        return false;
      }} onChange={event => { setFiles(event.fileList); setErrors([]); setCompleted(0); }}>
        <p className="ant-upload-drag-icon"><InboxOutlined aria-hidden /></p><p>拖放图片或点击选择文件</p><p className="subtle">支持 JPG、PNG、WebP、GIF，可选择多个文件。</p>
      </Upload.Dragger>
      <div className="image-upload-fields"><Form.Item name="title" label="标题" extra="留空时使用各文件的文件名。"><Input /></Form.Item>
        <Form.Item name="description" label="描述"><Input.TextArea rows={2} placeholder="描述图片内容，便于搜索匹配" /></Form.Item>
        <Form.Item name="tags" label="标签"><Input placeholder="用逗号分隔" /></Form.Item><Form.Item name="category" label="分类"><Select options={uploadCategories} /></Form.Item>
      </div>
    </Form>
    {pending && <div role="status"><Progress percent={Math.round(completed / files.length * 100)} />已处理 {completed} / {files.length} 个文件，请等待上传完成。</div>}
    {errors.length > 0 && <Alert type="error" title="部分文件未上传" description={<ul>{errors.map(error => <li key={error}>{error}</li>)}</ul>} />}
  </Modal>;
}
