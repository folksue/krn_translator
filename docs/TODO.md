# TODO

## 当前优先级（先完成）
- [x] 继续全量生成 `output/krn_final/*.krn`（断点续跑）
- [x] 产出最终统计：总条目、成功数、失败数、失败原因摘要
- [x] 抽样检查 `.krn` 头部元数据与小节结构

## 第二阶段（等 krn 完成后再做）
- [x] 编写 `src/convert_hooktheory_to_midi.py`（代码已完成，暂未跑全量）
- [x] 编写 `src/convert_hooktheory_to_musicxml.py`（代码已完成，暂未跑全量）
- [x] 编写 `src/validate_random_10.py`：随机抽 10 条，分别验证 JSON->KRN / JSON->MIDI / JSON->MusicXML 输出完整性

## 交付补充
- [x] 更新 `README.md`：运行方法、输出目录、文件命名、注意事项
- [ ] 准备可提交到 GitHub 的文件清单
