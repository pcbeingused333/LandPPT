import test from 'node:test';
import assert from 'node:assert/strict';
import { outlineGroups, outlineParent, outlineTree } from '../src/components/editor-outline-tree.ts';

const pages = [
  { key: 'cover', title: '封面', slideType: 'title' },
  { key: 'one', title: '背景与目标', slideType: 'transition' },
  { key: 'two', title: '市场资料', slideType: 'content' },
  { key: 'three', title: '目标总结', slideType: 'content' },
  { key: 'four', title: '实施计划', slideType: 'section' },
  { key: 'five', title: '流程与职责', slideType: 'content' },
];
test('explicit chapter pages own subsequent pages and preserve absolute indices', () => {
  const tree = outlineTree(pages);
  assert.deepEqual(tree.map(node => node.key), ['cover', 'one', 'four']);
  assert.deepEqual(tree[1].children.map(node => [node.key, node.index]), [['two', 2], ['three', 3]]);
  assert.equal(outlineParent(tree, 'five'), 'four');
  assert.equal(outlineParent(tree, 'cover'), undefined);
});
test('ordinary titles never create inferred chapters and empty decks stay empty', () => {
  assert.deepEqual(outlineTree([]), []);
  const flat = outlineTree([{ key: 'page', title: '第一章 背景', slideType: 'content' }]);
  assert.equal(flat[0].chapter, false); assert.equal(flat[0].children, undefined);
});
test('page search retains its chapter and original index rather than filtered position', () => {
  const tree = outlineTree(pages, ' 职责 ');
  assert.equal(tree[0].key, 'four'); assert.equal(tree[0].children[0].index, 5);
  assert.equal(outlineTree(pages, '3')[0].children[0].key, 'two');
});
test('matching a chapter exposes its pages while absent titles yield no results', () => {
  assert.deepEqual(outlineTree(pages, '背景')[0].children.map(node => node.key), ['two', 'three']);
  assert.deepEqual(outlineTree(pages, '不存在'), []);
  assert.equal(outlineTree([{ key: 'empty', title: '' }])[0].title, '未命名');
});
test('reordering/removing pages updates grouping without mutating source metadata', () => {
  const before = structuredClone(pages);
  const tree = outlineTree([pages[0], pages[4], pages[2], pages[1], pages[5]]);
  assert.equal(outlineParent(tree, 'two'), 'four'); assert.equal(outlineParent(tree, 'five'), 'one');
  assert.equal(tree[2].index, 3); assert.deepEqual(pages, before);
});

test('overview groups include each page once in reading order without inventing chapters', () => {
  const before = structuredClone(pages), groups = outlineGroups(pages);
  assert.deepEqual(groups.map(group => [group.title, group.chapter]), [['未分章节', false], ['背景与目标', true], ['实施计划', true]]);
  assert.deepEqual(groups.flatMap(group => group.pages.map(page => page.key)), pages.map(page => page.key));
  assert.deepEqual(pages, before); assert.deepEqual(outlineGroups([]), []);
  assert.equal(outlineGroups([pages[0], pages[2]])[0].title, '全部页面');
});

test('overview filtering retains explicit ancestors and absolute indices, including empty chapters', () => {
  const groups = outlineGroups(pages, '职责');
  assert.deepEqual(groups[0].pages.map(page => page.index), [4, 5]);
  assert.equal(outlineGroups([pages[1], pages[4]])[0].pages.length, 1);
  assert.deepEqual(outlineGroups(pages, 'missing'), []);
  assert.equal(outlineGroups([pages[4], pages[2], pages[1]], '3')[0].pages[0].key, 'one');
});
