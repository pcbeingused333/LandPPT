import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Descriptions, Drawer, Flex, Space, Typography } from 'antd';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ApiData } from '../api';
import { fileSize } from './images';

function MediaPlayer({ file }: { file: ApiData }) {
  const media = useRef<HTMLMediaElement | null>(null);
  const [failed, setFailed] = useState(false), [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const player = media.current;
    return () => {
      // Stop playback and release the network stream immediately, including
      // while the Drawer is still animating closed.
      player?.pause(); player?.removeAttribute('src'); player?.load();
    };
  }, [attempt, failed]);
  const Player = file.preview_kind === 'video' ? 'video' : 'audio';
  return <Space orientation="vertical" size="middle" className="artifact-media-player">
    {failed ? <Alert showIcon type="error" title="暂时无法播放" description="文件可能已过期、已移除，或浏览器不支持此编码。可重试或下载后查看。" action={<Button icon={<ReloadOutlined aria-hidden />} onClick={() => { setFailed(false); setAttempt(value => value + 1); }}>重试预览</Button>} />
      : <Player key={attempt} ref={node => { media.current = node; }} aria-label={file.preview_kind === 'video' ? '视频播放器' : '音频播放器'} controls preload="none" playsInline src={`/api/artifact-library/${encodeURIComponent(file.id)}/preview`} onError={() => setFailed(true)} />}
    <Typography.Text type="secondary">点击播放器开始预览。播放效果取决于浏览器对该文件编码的支持。</Typography.Text>
  </Space>;
}

export function ArtifactMediaPreview({ file, close, afterClose }: { file: ApiData | null; close: () => void; afterClose: () => void }) {
  return <Drawer title="音视频预览" open={!!file} onClose={close} size={640} destroyOnHidden className="artifact-media-preview" styles={{ wrapper: { maxWidth: '100vw' } }} afterOpenChange={open => { if (!open) afterClose(); }}
    footer={<Flex justify="flex-end" gap={8}><Button onClick={close}>关闭</Button>{file && <Button type="primary" href={`/api/artifacts/${encodeURIComponent(file.id)}/download`} download icon={<DownloadOutlined aria-hidden />}>下载文件</Button>}</Flex>}>
    {file && <Space orientation="vertical" size="large" className="artifact-media-body">
      <Typography.Paragraph strong ellipsis={{ rows: 2, tooltip: file.filename }} className="artifact-media-filename">{file.filename}</Typography.Paragraph>
      <MediaPlayer key={file.id} file={file} />
      <Descriptions size="small" column={1} items={[
        { key: 'type', label: '文件类型', children: file.category_label },
        { key: 'size', label: '文件大小', children: typeof file.file_size === 'number' ? fileSize(file.file_size) : '大小未知' },
        { key: 'created', label: '生成时间', children: file.created_at ? new Date(file.created_at * 1000).toLocaleString('zh-CN', { hour12: false }) : '时间未知' },
        { key: 'project', label: '所属项目', children: file.project ? <Typography.Link href={`/projects/${encodeURIComponent(file.project.id)}`}>{file.project.title}</Typography.Link> : '未关联项目' },
        ...(file.expires_at ? [{ key: 'expires', label: '有效期至', children: new Date(file.expires_at * 1000).toLocaleString('zh-CN', { hour12: false }) }] : []),
      ]} />
    </Space>}
  </Drawer>;
}
