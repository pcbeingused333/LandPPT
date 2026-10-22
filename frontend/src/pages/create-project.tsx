import { Button } from 'antd';
import type { ApiData } from '../api';
import CreateComposer from '../components/create-composer';

export default function CreateProject({ data }: { data: ApiData }) {
  return <div className="create-project-page">
    <div className="page-heading"><div><h1>创建 PPT</h1><p>填写主题与资料，设定生成方式。</p></div><Button href="/projects">项目列表</Button></div>
    <CreateComposer data={data} />
  </div>;
}
