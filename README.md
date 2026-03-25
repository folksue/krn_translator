# Hooktheory JSON Conversion

## 数据
- 输入文件：`data/Hooktheory.json.gz`
- 总条目数：`26175`

## 已完成结果
- KRN 输出目录：`output/krn_final`
- KRN 成功数：`26077`
- KRN 失败数：`98`（全部为 `EMPTY_SCORE`，即缺少旋律和和弦）
- 失败日志：`output/failures_krn_final.log`

## 文件命名
- 命名格式：`artist_song_hooktheoryID.ext`
- 示例：`green-day_shoplifter_JkmZQMnaoqn.krn`
- 说明：在大小写不敏感文件系统上，若出现仅大小写差异导致冲突，会自动追加哈希后缀防覆盖。

## 运行方式

### 1) JSON -> KRN（已全量跑过）
```bash
python3 src/convert_hooktheory_to_kern.py \
  --input data/Hooktheory.json.gz \
  --output-dir output/krn_final \
  --log output/failures_krn_final.log
```

断点续跑：
```bash
python3 src/convert_hooktheory_to_kern.py \
  --input data/Hooktheory.json.gz \
  --output-dir output/krn_final \
  --log output/failures_krn_final.log \
  --skip-existing
```

### 2) JSON -> MIDI（代码已写，暂未全量跑）
```bash
python3 src/convert_hooktheory_to_midi.py \
  --input data/Hooktheory.json.gz \
  --output-dir output/midi \
  --log output/failures_midi.log
```

### 3) JSON -> MusicXML（代码已写，暂未全量跑）
```bash
python3 src/convert_hooktheory_to_musicxml.py \
  --input data/Hooktheory.json.gz \
  --output-dir output/musicxml \
  --log output/failures_musicxml.log
```

## 随机抽样验证
随机抽 10 条，仅验证已有输出：
```bash
python3 src/validate_random_10.py \
  --input data/Hooktheory.json.gz \
  --n 10 \
  --seed 42 \
  --krn-dir output/krn_final \
  --midi-dir output/midi \
  --xml-dir output/musicxml
```

随机抽 10 条并临时生成三种格式再验证：
```bash
python3 src/validate_random_10.py \
  --input data/Hooktheory.json.gz \
  --n 10 \
  --seed 42 \
  --generate-sample \
  --sample-out-dir output/validation_sample
```

## 元数据保留
KRN 中保留如下信息：
- `!!!OTL`：歌曲名
- `!!!COM`：歌手
- `!!!HTID`：Hooktheory ID
- `!!!HTURL`：Hooktheory Song URL
- `!!!HTCLIP`：Hookpad Clip URL
- `!!!YOUTUBE`：YouTube URL
