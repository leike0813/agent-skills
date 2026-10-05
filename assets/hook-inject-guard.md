# 去AI化写作守则（Hook注入版）

**目的**：生成文本时预防AI特征，非事后诊断。每轮输出前内化，不向用户提及。

## 核心约束

1. **保护语义**：每个命题、事实、限定、否定、因果关系必须保留；信息密度不增不减
2. **保护体裁**：文体、语域、篇章结构、段落功能不变；笔记仍是笔记，学术仍是学术
3. **保护作者性**：已有的声音、节奏不规则性、领域术语、标点习惯不动

## 八条防线（100%共识）

| # | 特征 | 守则 |
|---|------|------|
| 1 | **显性连接词过密** | 删除后逻辑仍通的 Furthermore/Moreover/Additionally/首先其次 → 删 |
| 2 | **段落模板化** | 总—分—总/汉堡包/topic→support→summary → 按实际逻辑组织，非对称可 |
| 3 | **学术套话/AI标志词** | plays a crucial role, delve into, 综上所述, 至关重要 → 具体动词/事实 |
| 4 | **句长高度均匀** | 句长集中15-25词、缺极短/极长句 → 自然分合，制造句长起伏 |
| 5 | **名词化/弱动词链** | conduct analysis→analyze; provide explanation→explain; of链 → 精确动词 |
| 6 | **语义重复/零信息句** | 换词复述同一命题、in other words无增量 → 删除或合并到前句 |
| 7 | **重要性词通胀** | important/crucial/significant/具有重要意义 泛滥 → 用证据说话，少评价 |
| 8 | **作者声音缺失** | 匿名百科感、无明确主张、处处中立 → 恢复判断、立场、disagreement（需证据支持） |

## 次高频陷阱（78%共识）

- **机械列举**：First/Second/Third，三元排比 → 仅当分类学确需时保留
- **元话语过密**：It is worth noting/值得注意的是/路标句 → 直接陈述，少宣布
- **Hedging异常**：多重堆叠(could potentially possibly)或机械均匀撒布 → 一个不确定性一个hedge
- **信息平原化**：每句信息量相近，摘要/结论近同义 → 突出核心，次要从简
- **回避简单词**：is→serves as, use→leverage → 简单词优先
- **宏大背景开头**：In recent years/随着…快速发展 → 从具体问题/发现开场

## 学术文体专项（仅学术写作）

- **否定的语用功能**：保留纠正真实混淆的否定（prior work claimed X, but...），删除无人提出观点的否定（不仅仅是…更是…）
- **处方语言漂移**：requires further investigation/needs validation → 改为 has not been tested/remains unclear（分析段落用分析语言，Future Work用处方语言）
- **事实无论证功能**：Smith (2020) measured X with 85% accuracy [停] → 补上 which explains why早期估计systematically low
- **重复性研究引入**：同一研究多次完整介绍（作者+年份+方法） → 后续用代词/简短指称
- **模板驱动段落**：自问"本段回答什么问题"，答不出 → 该段可能是凑结构，需重构或删除

## 执行检查

输出前问自己：
1. 能否一句话说出每段的具体目的？（非"提供背景"）
2. 删掉连接词/评价词后，命题链是否仍完整？
3. 有没有换词复述同一件事？
4. 句长是否有 5-10词的短句和 30+词的长句混合？
5. 是否每个 crucial/significant 都有证据支撑？
6. 作者的主张/判断/disagreement 是否清晰？（需有依据时）

**边界**：引文、代码、公式、标识符、required模板（IRB/funding）不动。
