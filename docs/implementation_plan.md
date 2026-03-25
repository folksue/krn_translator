# Hooktheory JSON -> Humdrum Kern 作业计划

## 目标
- 从 `Hooktheory.json.gz` 读取所有歌曲条目。
- 将每首歌转换为可被 Verovio/Humdrum 渲染的 `.krn` 文件。
- 输出文件命名格式：`歌手_歌曲_hooktheoryID.krn`。
- 在 `.krn` 中保留元数据：歌曲名、歌手名、Hooktheory 链接、YouTube 链接等。

## 步骤
1. 分析 JSON 数据结构，确认旋律、和弦、调号、拍号、时值字段格式。
2. 设计字段映射到 Kern 的规则：
   - 调号/谱号/拍号头信息。
   - 音高（scale degree -> pitch）与时值（beats -> kern duration）。
   - 和弦字段映射为 `**mxhm`（文本和弦）spine。
3. 实现批量转换脚本 `src/convert_hooktheory_to_kern.py`。
4. 生成输出目录 `output/krn` 全量 `.krn`。
5. 抽样验证输出文件是否可被 Verovio 渲染（语法正确）。
6. 编写使用说明 `README.md`。

## 验收标准
- 脚本可一键运行。
- 输出文件数量与输入歌曲条目数量一致（可排除异常条目并记录）。
- 随机抽样的 `.krn` 能在 https://verovio.humdrum.org/ 正常渲染。
