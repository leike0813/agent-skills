# 论文领域分类

## 1. 实验 / 观察型自然科学论文

- Canonical domain name: `experimental-observational-natural-science`
- 适用领域： 物理、化学、生物、材料、环境、地球科学、部分农学等。
- 核心问题： 通过实验、观测或测量来回答因果、机制、性质或规律问题。
- 典型结构： Introduction → Methods → Results → Discussion，也就是 IMRaD 或其变体。ICMJE 对医学期刊稿件的建议中也说明，原创研究通常分为 Introduction、Methods、Results、Discussion，且这种结构反映科学发现过程，而不只是任意格式。

- 这类文档应重点指导：

 | 部分 | 写作重点 | 
 | --- | --- | 
 | Introduction | 现象、机制缺口、研究问题、假设 | 
 | Methods | 材料、设备、条件、变量、可重复性 | 
 | Results | 数据呈现、图表逻辑、主要发现 | 
 | Discussion | 解释机制、对比文献、边界条件、异常结果 | 
 | Conclusion | 发现的科学意义，而不是简单重复结果 | 

- 评审最关心： 方法是否可靠、结果是否支持结论、是否有机制解释、是否可重复。

## 2. 工程 / 系统 / 设计型论文

- Canonical domain name: `engineering-system-design`
- 适用领域： 工程、机器人、HCI、软件系统、网络系统、芯片、控制、能源系统、智能制造等。
- 核心问题： 提出一个系统、方法、流程、装置、架构或工程方案，并证明它比已有方案更好。
- 典型结构：
```
Problem / Requirements → Design → Implementation → Evaluation → Discussion
```
- 这类文档应重点指导：

 | 部分 | 写作重点 | 
 | --- | --- | 
 | Problem | 真实约束、性能瓶颈、需求场景 | 
 | Design | 设计原则、系统架构、关键模块 | 
 | Implementation | 工程细节、参数、复杂度、可部署性 | 
 | Evaluation | 指标、基线、消融、压力测试、案例 | 
 | Discussion | 局限、可扩展性、失败场景 | 

评审最关心： 问题是否真实、设计是否合理、实验是否公平、系统是否可复现、指标是否有说服力。

这一类不能简单套用自然科学 IMRaD。工程论文往往不是“发现一个自然规律”，而是“构造一个可验证的解决方案”。

## 3. 计算 / 算法 / 数据驱动型论文

- Canonical domain name: `computational-algorithm-data-driven`
- 适用领域： 计算机科学、AI、机器学习、数据科学、生物信息学、计算社会科学、计算物理等。
- 核心问题： 提出模型、算法、数据集、评价框架或计算方法，并通过理论、实验或 benchmark 证明有效。

- 典型结构：
```
Introduction → Related Work → Method / Model → Experiments → Results → Analysis → Limitations
```
- 这类文档应重点指导：

 | 部分 | 写作重点 | 
 | --- | --- | 
 | Problem setup | 任务定义、输入输出、假设 | 
 | Method | 模型结构、算法流程、损失函数、复杂度 | 
 | Experiment | 数据集、基线、指标、训练细节 | 
 | Result | 主结果、消融实验、鲁棒性、误差分析 | 
 | Reproducibility | 代码、数据、随机种子、计算资源 | 
 | Limitation | 泛化边界、偏差、失败案例 | 

- 评审最关心： 是否有真正方法贡献、实验是否公平、是否击败强基线、是否解释为什么有效。

这类文档应单列，不要并入“理工”。因为计算类论文的核心不是“实验室实验”，而是 方法—数据—评价协议 的三角关系。

## 4. 数学 / 理论 / 证明型论文

- Canonical domain name: `mathematical-theory-proof`
- 适用领域： 数学、理论计算机、理论物理、统计理论、经济理论、逻辑、形式化方法等。
- 核心问题： 提出定义、定理、模型、证明、性质或理论解释。

- 典型结构：
```
Introduction → Preliminaries → Main Results → Proofs → Examples / Applications → Discussion
```
- 这类文档应重点指导：

 | 部分 | 写作重点 | 
 | --- | --- | 
 | Introduction | 问题背景、已有理论缺口、主定理直觉 | 
 | Preliminaries | 定义、符号、假设、已有引理 | 
 | Main Results | 定理陈述、条件、意义 | 
 | Proof | 证明路线、关键构造、技术难点 | 
 | Examples | 反例、特例、应用场景 | 
 | Discussion | 理论影响、开放问题 | 

- 评审最关心： 定义是否清楚、定理是否重要、证明是否正确、结果是否比已有工作推进一步。

这类论文的写作指导应强调“读者先理解结论为何重要，再进入证明细节”。很多理论论文的问题不是证明不对，而是贡献不清楚。

## 5. 医学 / 临床 / 公共卫生论文

- Canonical domain name: `medical-clinical-public-health`
- 适用领域： 临床医学、流行病学、护理、公共卫生、药学、循证医学、健康政策等。
- 核心问题： 研究疾病、干预、诊断、预后、风险因素、健康服务或人群健康问题。

- 典型结构：
```
IMRaD + 研究类型报告规范
```
- 这一类必须单列，因为医学健康研究有非常强的报告规范生态。EQUATOR Network 明确提供健康研究报告指南数据库，并按主要研究类型列出随机试验、观察性研究、系统综述、诊断 / 预后研究、病例报告、定性研究、动物研究、经济评价等类别。 例如 CONSORT 2025 是随机试验报告指南，EQUATOR 页面说明其适用于随机试验报告。

- 这类文档应重点指导：

 | 研究类型 | 写作重点 | 
 | --- | --- | 
 | 随机对照试验 | CONSORT、分组、随机化、盲法、主要终点 | 
 | 观察性研究 | STROBE、暴露、结局、混杂控制 | 
 | 诊断 / 预后研究 | 敏感度、特异度、校准、验证 | 
 | 系统综述 | PRISMA、检索策略、纳排标准、偏倚风险 | 
 | 病例报告 | CARE、临床过程、诊断推理、启示 | 
 | 公共卫生研究 | 人群、政策背景、外部效度、伦理 | 

- 评审最关心： 伦理合规、研究设计、偏倚控制、统计分析、临床意义、报告透明度。

## 6. 定量社会科学 / 行为科学论文

- Canonical domain name: `quantitative-social-behavioral-science`
- 适用领域： 心理学、教育学、管理学、传播学、社会学、政治学、经济学中以数据分析为主的论文。
- 核心问题： 用调查、实验、准实验、面板数据、计量模型或统计模型解释社会行为、制度影响或心理机制。

- 典型结构：
```
Introduction → Theory / Hypotheses → Data / Method → Results → Robustness → Discussion
```
APA 的 JARS 体系也区分定量、定性和混合方法研究报告标准；这说明社会与行为科学中的“方法类型”本身就是写作规范的重要分界。

- 这类文档应重点指导：

 | 部分 | 写作重点 | 
 | --- | --- | 
 | Theory | 概念、机制、假设推导 | 
 | Data | 样本、变量、测量、数据来源 | 
 | Identification | 因果识别、模型选择、内生性处理 | 
 | Results | 主效应、效应量、显著性、不确定性 | 
 | Robustness | 替代变量、替代模型、异质性分析 | 
 | Discussion | 理论贡献、实践意义、边界条件 | 

- 评审最关心： 理论是否驱动假设、测量是否有效、识别策略是否可信、结果是否稳健。

这类文档不应与自然科学共用同一套 IMRaD 指南。它虽然也有 Methods 和 Results，但写作重心在 理论机制 + 研究设计 + 识别可信度。

## 7. 定性 / 解释型社会科学论文

- Canonical domain name: `qualitative-interpretive-social-science`
- 适用领域： 人类学、社会学、教育学、传播学、组织研究、社会工作、护理、文化研究中的访谈、田野、案例、话语分析等。
- 核心问题： 通过访谈、观察、文本、档案、案例或参与式研究来解释意义、经验、实践、制度或过程。

- 典型结构：
```
Introduction → Literature / Theory → Context → Methodology → Findings / Themes → Discussion
```
EQUATOR 收录的 APA 相关 JARS 条目明确说明，该报告标准适用于定性研究、混合方法研究和定性元分析，并列出 JARS-Qual、MMARS、QMARS 等清单。

- 这类文档应重点指导：

 | 部分 | 写作重点 | 
 | --- | --- | 
 | Research question | 不是变量关系，而是经验、意义、过程或机制 | 
 | Methodology | 研究立场、取样、资料收集、编码、分析路径 | 
 | Reflexivity | 研究者位置、解释边界、伦理关系 | 
 | Findings | 主题、叙事、概念、案例证据 | 
 | Discussion | 理论延展、概念贡献、情境化解释 | 

- 评审最关心： 材料是否充分、分析是否透明、解释是否有深度、是否避免“访谈摘录堆砌”。

## 8. 人文学科 / 文本解释 / 历史论证型论文

- Canonical domain name: `humanities-textual-historical`
- 适用领域： 文学、历史、哲学、艺术史、宗教学、语言学部分方向、思想史、古典学等。
- 核心问题： 围绕文本、史料、作品、概念、思想传统或文化现象提出解释性论点。

- 典型结构：
```
Thesis-driven Argument → Evidence-based Sections → Interpretive Development → Conclusion
```
- 这类文档应重点指导：

 | 部分 | 写作重点 | 
 | --- | --- | 
 | Introduction | 研究对象、学术争议、本文论点 | 
 | Literature / Debate | 不是“综述所有文献”，而是定位解释分歧 | 
 | Body sections | 每一节推进一个子论点 | 
 | Evidence | 文本细读、史料、概念分析、语境化材料 | 
 | Conclusion | 解释贡献、理论意义、重新理解对象 | 

- 评审最关心： 论点是否原创、材料解读是否细致、是否进入学术争论、论证是否层层推进。

这类论文不适合强行套 IMRaD。它的核心不是“方法—结果”，而是 问题意识—材料解释—论证推进。

## 9. 法学 / 规范 / 政策分析型论文

- Canonical domain name: `law-normative-policy-analysis`
- 适用领域： 法学、伦理学、公共政策、治理研究、制度分析、科技伦理、部分国际关系研究等。
- 核心问题： 评价规范、制度、政策、规则或价值冲突，并提出解释、批判或改进方案。

- 典型结构：
```
Problem → Legal / Normative Framework → Analysis → Counterarguments → Proposal / Implications
```
- 这类文档应重点指导：

 | 部分 | 写作重点 | 
 | --- | --- | 
 | Problem | 现实争议、制度缺口、规范冲突 | 
 | Framework | 法条、判例、原则、伦理理论、政策目标 | 
 | Analysis | 适用、解释、比较、后果评估 | 
 | Counterarguments | 反方理由、权衡、限制 | 
 | Proposal | 修法建议、政策路径、治理原则 | 

- 评审最关心： 问题是否真实、规范框架是否准确、推理是否严密、反驳是否充分、建议是否可行。

这一类很容易被“社科”吞掉，但它的写作逻辑和经验社科很不同：核心不是数据发现，而是 规范推理、制度解释和价值权衡。
