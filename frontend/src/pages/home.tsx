import { useState } from 'react';
import { Button } from 'antd';
import { ArrowRightOutlined, ArrowUpOutlined, FileTextOutlined, PlayCircleOutlined, AppstoreOutlined, EditOutlined, SoundOutlined, DownloadOutlined } from '@ant-design/icons';
import type { ApiData } from '../api';
import HomeSponsors from './home-sponsors';
import './home.css';

const examples = [
  { label: '产品叙事', title: '把下一步，讲清楚。', subtitle: '从一个想法，到一场有说服力的发布。', theme: 'story', heading: <>Ideas<br />into impact.</>, kicker: 'THE NEXT CHAPTER', footer: '产品发布 / 品牌提案' },
  { label: '数据洞察', title: '让数据有观点。', subtitle: '清晰的结构，让每一个结论都有支撑。', theme: 'data', heading: <>Beyond<br />the numbers.</>, kicker: 'A CLEARER PERSPECTIVE', footer: '业务复盘 / 研究报告' },
  { label: '知识分享', title: '让知识被理解。', subtitle: '从问题出发，把复杂的内容层层展开。', theme: 'lesson', heading: <>Make room<br />for discovery.</>, kicker: 'LEARNING, REIMAGINED', footer: '课程讲解 / 知识分享' },
];

const workflow = [
  { number: '01', title: '带来你的想法', description: '输入主题与需求，或添加文档、网页资料。让散落的信息成为创作的起点。', icon: <FileTextOutlined aria-hidden /> },
  { number: '02', title: '找到表达的方式', description: '确认内容大纲，选择自由设计或模板包。把逻辑与视觉放在同一条创作路径上。', icon: <AppstoreOutlined aria-hidden /> },
  { number: '03', title: '打磨，然后登场', description: '逐页编辑，补充讲稿与配音，预览并导出。把最后一处细节也掌握在自己手里。', icon: <PlayCircleOutlined aria-hidden /> },
];

const capabilities = [
  { icon: <EditOutlined aria-hidden />, title: '好内容，可以继续打磨', description: '编辑大纲、讲稿与幻灯片，用 AI 调整内容与布局，让表达更贴近你的意图。' },
  { icon: <AppstoreOutlined aria-hidden />, title: '好设计，有自己的风格', description: '自由设计探索不同表达；模板包保持整套演示的一致，也能从 PPTX 创建自己的模板包。' },
  { icon: <SoundOutlined aria-hidden />, title: '好演示，也能被听见', description: '生成逐页讲稿与语音讲解，进一步制作讲解视频，让演示离开会议室也能被理解。' },
  { icon: <DownloadOutlined aria-hidden />, title: '带着作品，去任何地方', description: '按分享场景选择 PPTX、PDF、HTML 或图片；讲稿也可以导出为 DOCX 与 Markdown。' },
];

function SlideArt({ theme }: { theme: string }) {
  if (theme === 'data') return <div className="home-data-art" aria-hidden>
    <div className="home-data-trend"><ArrowUpOutlined /><span>看见趋势</span></div>
    <div className="home-data-bars">{[30, 44, 38, 61, 72, 92].map((height, index) => <span key={index} style={{ height: `${height}%` }} />)}</div>
    <div className="home-data-axis"><span>观察</span><span>洞察</span><span>行动</span></div>
  </div>;
  if (theme === 'lesson') return <div className="home-lesson-art" aria-hidden><span /><span /><span /><span /><div>从好奇<br />到发现</div></div>;
  return <svg className="home-orbit-art" viewBox="0 0 360 360" fill="none" aria-hidden="true">
    <circle cx="180" cy="180" r="139" /><circle cx="180" cy="180" r="105" /><circle cx="180" cy="180" r="71" />
    <ellipse cx="180" cy="180" rx="139" ry="49" transform="rotate(-38 180 180)" />
    <path d="M41 180H319M180 41V319" /><circle cx="267" cy="71" r="12" className="home-orbit-point" />
    <circle cx="180" cy="180" r="24" className="home-orbit-center" />
  </svg>;
}

export default function Home({ data }: { data: ApiData }) {
  const [selected, setSelected] = useState(0);
  const example = examples[selected];
  return <div className="home-showcase">
    <section className="home-hero home-wrap" aria-labelledby="homeTitle">
      <div className="home-hero-copy">
        <h1 id="homeTitle">让想法，<br /><span>成为好演示。</span></h1>
        <p className="home-lead">从第一句灵感，到最后一页呈现。<br />用 AI 整理内容、设计页面，<br className="home-mobile-break" />也为你留下每一步的创作空间。</p>
        <div className="home-hero-actions"><Button type="primary" href="/dashboard" icon={<ArrowRightOutlined aria-hidden />} iconPlacement="end">开始创建 PPT</Button></div>
      </div>
      <figure className="home-showreel" aria-label="演示设计示例">
        <div className={`home-deck home-deck-${example.theme}`}>
          <div className="home-deck-inner" key={example.theme}>
            <div className="home-slide-top"><span>LANDPPT / STUDIO</span><span>{String(selected + 1).padStart(2, '0')}</span></div>
            <div className="home-slide-copy"><span>{example.kicker}</span><h2>{example.heading}</h2><p>{example.title}</p></div>
            <SlideArt theme={example.theme} />
            <div className="home-slide-bottom"><span>{example.footer}</span><span>AN IDEA WORTH SHARING ↗</span></div>
          </div>
        </div>
        <figcaption><div className="home-example-caption" aria-live="polite" aria-atomic="true"><strong>{example.title}</strong><span>{example.subtitle}</span></div><span className="home-example-count">0{selected + 1}<span> / 03</span></span></figcaption>
        <div className="home-example-options" role="group" aria-label="切换设计示例">{examples.map((item, index) => <button type="button" key={item.theme} aria-pressed={selected === index} onClick={() => setSelected(index)}><span aria-hidden>0{index + 1}</span>{item.label}<ArrowRightOutlined aria-hidden /></button>)}</div>
      </figure>
    </section>

    <HomeSponsors sponsors={data.sponsors || []} />

    <section className="home-workflow home-wrap" aria-labelledby="homeWorkflowTitle">
      <div className="home-section-heading"><h2 id="homeWorkflowTitle">从想法出发，<br />一路走到呈现。</h2></div>
      <ol className="home-workflow-list" aria-label="创建流程">{workflow.map(step => <li key={step.number}><div className="home-workflow-top"><span>{step.number}</span>{step.icon}</div><h3>{step.title}</h3><p>{step.description}</p></li>)}</ol>
    </section>

    <section className="home-capabilities" aria-labelledby="homeCapabilitiesTitle"><div className="home-capabilities-inner home-wrap">
      <div className="home-capabilities-intro"><h2 id="homeCapabilitiesTitle">好演示，<br />不止好看。</h2><p>AI 帮你起步，<br />创作的主动权始终在你手里。</p><a className="home-text-link" href="/global-master-templates">探索模板库 <ArrowRightOutlined aria-hidden /></a><div className="home-paper-stack" aria-hidden><div /><div /><div><span>YOUR<br /><em>next</em><br />BIG IDEA.</span><span>从这里开始 ↗</span></div></div></div>
      <div className="home-capability-list">{capabilities.map(item => <article key={item.title}><span className="home-capability-icon">{item.icon}</span><div><h3>{item.title}</h3><p>{item.description}</p></div></article>)}</div>
    </div></section>

    <section className="home-finale home-wrap" aria-labelledby="homeFinaleTitle"><h2 id="homeFinaleTitle">下一场精彩，<br />从你的想法开始。</h2><Button href="/dashboard" icon={<ArrowRightOutlined aria-hidden />} iconPlacement="end">创建我的演示文稿</Button></section>
  </div>;
}
