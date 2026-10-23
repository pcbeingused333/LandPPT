import type { ReactNode } from 'react';
import { Button, Flex, Grid, Steps, Tooltip } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { navigatePage } from '../navigation';

// Facts come from the server (components/project/workspace_state.html); the bar
// only reads them and links to existing routes, never starts or skips work.
export type WorkspaceState = { hasOutline?: boolean; hasTemplate?: boolean; hasOutput?: boolean; outlineRunning?: boolean; generating?: boolean };
export type WorkspaceStage = 'planning' | 'design' | 'generate' | 'deliver';
type Status = 'wait' | 'process' | 'finish' | 'error';

const order: WorkspaceStage[] = ['planning', 'design', 'generate', 'deliver'];
const titles: Record<WorkspaceStage, string> = { planning: '内容规划', design: '视觉设计', generate: '页面生成', deliver: '编辑交付' };

export function workspaceStages(projectId: string, state: WorkspaceState = {}, generating = !!state.generating) {
  const base = `/projects/${encodeURIComponent(projectId)}`;
  const { hasOutline = false, hasOutput = false } = state;
  const hasDesign = !!state.hasTemplate || hasOutput;
  const status: Record<WorkspaceStage, Status> = {
    planning: hasOutline ? 'finish' : 'process',
    design: hasDesign ? 'finish' : hasOutline ? 'process' : 'wait',
    generate: generating ? 'process' : hasOutput ? 'finish' : hasOutline && hasDesign ? 'process' : 'wait',
    deliver: hasOutput && !generating ? 'process' : 'wait',
  };
  const links: Record<WorkspaceStage, string | undefined> = {
    planning: `${base}/todo?view=planning`,
    design: hasOutline && !generating ? `${base}/template-selection` : undefined,
    generate: hasOutline && hasDesign ? `${base}/todo` : undefined,
    deliver: hasOutput ? `${base}/edit` : undefined,
  };
  const hints: Record<WorkspaceStage, string> = {
    planning: hasOutline ? '查看与修改大纲' : '确认需求并生成大纲',
    design: generating ? '生成进行中，完成后可调整设计' : hasOutline ? '选择模板或设计方式' : '完成大纲后可选择设计',
    generate: hasOutline && hasDesign ? generating ? '查看实时生成进度' : '查看生成结果与进度' : '选择设计后开始生成',
    deliver: hasOutput ? '编辑页面、讲稿并导出' : '生成页面后可编辑',
  };
  return order.map(key => ({ key, title: titles[key], status: status[key], link: links[key], hint: hints[key] }));
}

export function activeStage(state: WorkspaceState = {}): WorkspaceStage {
  return state.generating ? 'generate' : state.hasOutput ? 'deliver' : state.hasOutline ? state.hasTemplate ? 'generate' : 'design' : 'planning';
}

// `current` marks the page being shown; on hub pages (`hub`) it marks the project's active stage instead.
export function ProjectStages({ projectId, state, current, generating, hub = false }: { projectId: string; state?: WorkspaceState; current: WorkspaceStage; generating?: boolean; hub?: boolean }) {
  const screens = Grid.useBreakpoint();
  const stages = workspaceStages(projectId, state, generating);
  const index = order.indexOf(current);
  return <nav className="project-stages" aria-label="创作阶段">
    <Steps size="small" type={screens.md ? 'navigation' : 'default'} responsive={false} current={index}
      onChange={next => { const link = stages[next].link; if ((hub || next !== index) && link) navigatePage(link); }}
      items={stages.map((stage, position) => ({
        title: <Tooltip title={stage.hint}><span aria-current={!hub && position === index ? 'step' : undefined}>{stage.title}</span></Tooltip>,
        status: stage.status, disabled: !stage.link && (hub || position !== index),
      }))} />
  </nav>;
}

export function ProjectWorkspaceHeader({ back, eyebrow, title, meta, actions, stages }: { back: { href: string; label: string }; eyebrow?: ReactNode; title: string; meta?: ReactNode; actions?: ReactNode; stages: ReactNode }) {
  return <header className="project-workspace-header">
    <Flex className="project-workspace-top" align="center" gap={12} wrap>
      <Tooltip title={back.label}><Button href={back.href} aria-label={back.label} icon={<ArrowLeftOutlined aria-hidden />} /></Tooltip>
      <div className="project-workspace-title">{eyebrow && <span className="project-workspace-eyebrow">{eyebrow}</span>}<h1 title={title}>{title}</h1>{meta && <div className="project-workspace-meta">{meta}</div>}</div>
      {actions && <div className="project-workspace-actions">{actions}</div>}
    </Flex>
    {stages}
  </header>;
}
