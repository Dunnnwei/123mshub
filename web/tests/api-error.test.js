import test from 'node:test'
import assert from 'node:assert/strict'

import { formatErrorDetail } from '../src/api.js'


test('422 校验错误数组会转成字段名加原因的可读文本', () => {
  const detail = [
    { type: 'literal_error', loc: ['body', 'provider'], msg: "Input should be 'local' or 'github'" },
  ]

  assert.equal(
    formatErrorDetail(detail),
    "provider：Input should be 'local' or 'github'",
  )
})

test('多条校验错误用分号连接，去掉 loc 里的 body 前缀', () => {
  const detail = [
    { type: 'string_type', loc: ['body', 'source_url'], msg: 'Input should be a valid string' },
    { type: 'missing', loc: ['body', 'name'], msg: 'Field required' },
  ]

  assert.equal(
    formatErrorDetail(detail),
    'source_url：Input should be a valid string；name：Field required',
  )
})

test('对象 detail 取 msg 字段，字符串原样返回，空值返回空串', () => {
  assert.equal(formatErrorDetail({ msg: '服务器内部错误' }), '服务器内部错误')
  assert.equal(formatErrorDetail('来源地址无法解析'), '来源地址无法解析')
  assert.equal(formatErrorDetail(undefined), '')
  assert.equal(formatErrorDetail(null), '')
})
