import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createAssistantMessage,
  withMessageId,
  mergeConversation,
  filterConversationForDisplay,
  formatAssistantContent,
  stripOptionsMarkup,
  stripContextPrefix,
} from './chatMessage.js';

test('旧版效果完成消息显示为简洁摘要', () => {
  const content = [
    'Left Wrist Growing Ring is ready. Adjust its controls in the Parameters panel.',
    '',
    'Parameters:',
    '  Ring color — Changes the luminous cyan tone',
    '  Start radius — Sets the compact ring size',
  ].join('\n');

  assert.equal(
    formatAssistantContent(content),
    'Left Wrist Growing Ring is ready.\n2 controls available in Parameters.',
  );
});

test('普通助手消息不会被显示格式化器改写', () => {
  assert.equal(formatAssistantContent('Open Parameters for details.'), 'Open Parameters for details.');
});

test('普通回复转换为基础助手消息', () => {
  const message = createAssistantMessage({ response: '已经完成' });

  assert.deepEqual(message, {
    role: 'assistant',
    content: '已经完成',
  });
});

test('withMessageId 为消息附加唯一编号且保留原字段', () => {
  const message = withMessageId({ role: 'user', content: '你好' });

  assert.equal(message.role, 'user');
  assert.equal(message.content, '你好');
  assert.ok(message.id);
});

test('mergeConversation：本地为空时直接采用历史并附编号', () => {
  const merged = mergeConversation([], [
    { role: 'user', content: '旧消息' },
    { role: 'assistant', content: '旧回复' },
  ]);

  assert.equal(merged.length, 2);
  assert.ok(merged[0].id);
});

test('mergeConversation：加载期间发出的本地消息与服务器副本只保留一份', () => {
  const local = [{ role: 'user', content: '做火焰', id: 'local-1' }];
  const merged = mergeConversation(
    local,
    [
      { role: 'user', content: '做火焰' },
      { role: 'assistant', content: '已生成火焰' },
    ],
    new Set(['user\u0000做火焰']),
  );

  assert.equal(merged.length, 2);
  assert.equal(merged[0].id, 'local-1');
  assert.equal(merged[1].role, 'assistant');
});

test('mergeConversation：两条相同的本地消息都保留，只跳过服务器副本', () => {
  const local = [
    { role: 'user', content: '再亮一点', id: 'l1' },
    { role: 'user', content: '再亮一点', id: 'l2' },
  ];
  const merged = mergeConversation(
    local,
    [{ role: 'user', content: '再亮一点' }],
    new Set(['user\u0000再亮一点']),
  );

  assert.equal(merged.length, 2);
  assert.equal(merged[0].id, 'l1');
  assert.equal(merged[1].id, 'l2');
});

test('追问回复保留标题和选项', () => {
  const options = [
    { label: '火焰', description: '手腕产生火焰拖尾' },
    { label: '闪电', description: '双手之间出现闪电' },
  ];

  const message = createAssistantMessage({
    response: '请选择一种效果',
    options_header: '你更喜欢哪种风格？',
    options,
  });

  assert.deepEqual(message, {
    role: 'assistant',
    content: '请选择一种效果',
    optionsHeader: '你更喜欢哪种风格？',
    options,
  });
});

test('空选项不会创建选项字段', () => {
  const message = createAssistantMessage({
    response: '请继续描述',
    options_header: '请选择',
    options: [],
  });

  assert.deepEqual(message, {
    role: 'assistant',
    content: '请继续描述',
  });
});

test('过滤对话历史：丢弃 tool 消息和空助手占位', () => {
  const conversation = [
    { role: 'user', content: '做一个红色圆点' },
    { role: 'assistant', content: '' },
    { role: 'tool', content: "{'status': 'submitted', 'code': 'class Effect...'}" },
    { role: 'assistant', content: '已生成红色圆点效果' },
  ];

  const display = filterConversationForDisplay(conversation);

  assert.deepEqual(display, [
    { role: 'user', content: '做一个红色圆点' },
    { role: 'assistant', content: '已生成红色圆点效果' },
  ]);
});

test('过滤对话历史：无内容时返回空数组', () => {
  assert.deepEqual(filterConversationForDisplay(), []);
  assert.deepEqual(filterConversationForDisplay([{ role: 'tool', content: 'x' }]), []);
});

test('去掉 <options> 标记：只保留问题文字', () => {
  const content = '请选择你想要的风格\n<options>\n<header>风格</header>\n<option label="火焰" description="拖尾"/>\n<option label="闪电" description="雷电"/>\n</options>\n也可以直接输入你的想法';

  const result = stripOptionsMarkup(content);

  assert.equal(result.includes('<options>'), false);
  assert.equal(result.includes('火焰'), false);
  assert.equal(result.includes('闪电'), false);
  assert.ok(result.includes('请选择你想要的风格'));
  assert.ok(result.includes('也可以直接输入你的想法'));
});

test('去掉 <options> 标记：普通消息不受影响', () => {
  assert.equal(stripOptionsMarkup('已生成火焰效果'), '已生成火焰效果');
  assert.equal(stripOptionsMarkup(''), '');
});

test('去掉旧档案上下文前缀：只留用户原话', () => {
  const content = '[当前视频 ID: 001]\n[当前效果:  (ID: abc)]\n[系统暂无已保存效果]\n\n选择：火焰';
  assert.equal(stripContextPrefix(content), '选择：火焰');
  assert.equal(stripContextPrefix('普通消息'), '普通消息');
  // 用户输入本身以 [ 开头也不误删（前缀后有空行分隔）
  assert.equal(stripContextPrefix('[系统暂无已保存效果]\n\n[你好]'), '[你好]');
});
