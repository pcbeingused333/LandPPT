import { Button } from 'antd';
import type { ApiData } from '../api';
import CreateComposer from '../components/create-composer';

export default function CreateProject({ data }: { data: ApiData }) {
  return <div className="create-project-page">
    <div className="page-heading"><h1>创建 PPT</h1><Button href="/projects">项目列表</Button></div>
    <CreateComposer data={data} />
  </div>;
}
