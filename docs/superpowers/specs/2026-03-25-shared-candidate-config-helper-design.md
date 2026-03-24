# Shared Candidate-Config Helper 设计

## 1. 背景

截至 2026-03-25，系统已经存在两条会消费 `candidate-config` 的 CLI 路径：

- `scripts/run_research.py`
- `scripts/run_research_governance_pipeline.py`

这两处目前各自维护一份 `_load_candidate_specs()`：

- 都读取 YAML
- 都按 `ResearchConfig(**data["research"])` 做校验
- 都返回 `candidate.model_dump()` 列表

除了生产脚本重复，测试侧也存在同类重复：

- `tests/test_research_pipeline.py`
- `tests/test_research_governance_pipeline.py`
- `tests/test_research_governance_pipeline_cli_smoke.py`

这些测试里分别手写：

- 最小 `candidate-config` YAML
- 更复杂的候选配置 YAML
- 对应的 `candidate_specs` 期望结构

当前问题不是功能缺失，而是共享逻辑分散：

- CLI 解析逻辑重复，后续一处改动容易漏另一处
- smoke / pipeline 测试反复拷贝候选配置样例
- 候选配置语义已经稳定，但还没有一个明确的共享边界

因此，B 子项目的目标不是新增能力，而是把 `candidate-config` 的生产解析与测试辅助收敛成明确、可复用、低耦合的一层。

## 2. 本子项目已确认选择

本子项目按以下边界设计：

- 抽共享 `candidate-config` 生产 helper
- 同时收敛 smoke / test 中的配置写入与 `candidate_specs` 断言辅助
- CLI 对外参数与运行语义保持不变
- 默认 research config 的加载语义保持不变
- 本轮只收敛 `candidate-config`
  - 不顺手抽 artifact 断言 helper
  - 不扩展到其他 YAML 配置类型

## 3. 目标

建设一层最小共享能力，使系统可以：

- 用单一生产 helper 解析外部 `candidate-config` YAML
- 让 `run_research` 与 `run_research_governance_pipeline` 共享同一套候选配置加载路径
- 用统一测试 support helper 生成候选配置样例与期望 `candidate_specs`
- 降低 CLI 与 smoke/test 的重复实现和后续漂移风险

## 4. 非目标

本子项目明确不做：

- 改写 `run_research_pipeline()` 或 `run_research_governance_pipeline()` 的运行语义
- 修改 `config_loader.load_research_config()` 的默认配置缓存/加载行为
- 新增自动发现配置文件、环境变量覆盖或多层 merge 规则
- 抽象 smoke 的 artifact 存在性断言
- 重构测试目录的大结构

## 5. 方案选择

本子项目采用：

- 生产 helper 下沉到 `src/`
- 测试辅助独立放在 `tests/support/`

而不是：

- 继续让两个 CLI 在 `scripts/` 层各自维护 `_load_candidate_specs()`
- 把外部 YAML 解析硬塞进 `src/core/config.py`
- 只抽生产 helper，不收敛 smoke/test 的配置样例

原因：

- `candidate-config` 是一项可复用的业务输入解析能力，应属于 `src/`，而不是只挂在某个脚本里
- `config_loader` 负责默认配置与全局缓存，外部临时 YAML 解析塞进去会污染职责边界
- 测试样例若不一起收敛，生产与测试仍会各自演化，重复问题只解决一半

## 6. 模块边界

### 6.1 生产层

建议新增：

- `src/research_candidate_config.py`

职责只包含：

- 读取外部 `candidate-config` YAML
- 基于 `ResearchConfig` 做结构校验
- 产出 CLI / service 可直接消费的 `list[dict[str, Any]]`

它不负责：

- 默认 `config/research.yaml` 的缓存加载
- research pipeline 主流程
- governance pipeline 编排

### 6.2 CLI 层

保留现有入口：

- `scripts/run_research.py`
- `scripts/run_research_governance_pipeline.py`

变更方式为：

- 删除各自本地 `_load_candidate_specs()` 实现
- 改为导入共享 helper

保持不变：

- `--candidate-config` 参数名
- 未传 `--candidate-config` 时向下游传 `None`
- 其他 runtime 参数转发行为

### 6.3 测试支持层

建议新增：

- `tests/support/research_candidates.py`

必要时补齐：

- `tests/support/__init__.py`

职责只包含：

- 提供稳定的候选配置样例
- 负责测试用 YAML 写入
- 负责构造期望 `candidate_specs`
- 提供轻量断言辅助

它不负责：

- smoke 的 artifact 断言
- monkeypatch 封装
- research / governance 运行结果的业务断言

## 7. 接口设计

### 7.1 生产 helper 接口

建议暴露两个函数：

```python
def load_candidate_specs(candidate_config: str | Path | None) -> list[dict[str, Any]] | None:
    ...


def parse_candidate_config_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    ...
```

语义约束：

- `candidate_config is None`：
  - 返回 `None`
  - 由下游保持当前“使用默认 research config”的语义
- `candidate_config` 有值：
  - 读取 YAML
  - 使用 `ResearchConfig(**data["research"])` 做校验
  - 返回 `[candidate.model_dump() for candidate in candidates]`

拆成两层的原因：

- `load_candidate_specs(...)` 处理路径读取
- `parse_candidate_config_data(...)` 处理纯数据校验与转换

这样既便于 CLI 调用，也便于做更小粒度的单测。

### 7.2 测试 support 接口

建议提供：

```python
DEFAULT_TEST_CANDIDATES = [...]
ADVANCED_TEST_CANDIDATES = [...]


def write_candidate_config(path: Path, candidates=DEFAULT_TEST_CANDIDATES) -> Path:
    ...


def expected_candidate_specs(candidates=DEFAULT_TEST_CANDIDATES) -> list[dict[str, Any]]:
    ...


def assert_candidate_specs(actual, candidates=DEFAULT_TEST_CANDIDATES) -> None:
    ...
```

语义约束：

- `DEFAULT_TEST_CANDIDATES` 用于 smoke 和最小 happy-path CLI 测试
- `ADVANCED_TEST_CANDIDATES` 用于覆盖复杂 `overrides`
- `assert_candidate_specs(...)` 只校验候选配置本身
  - 不掺入 artifact、退出码、stdout/stderr 断言

## 8. 文件边界

### Create

- `src/research_candidate_config.py`
- `tests/support/research_candidates.py`
- `tests/support/__init__.py`（若目录当前不存在则新增）

### Modify

- `scripts/run_research.py`
- `scripts/run_research_governance_pipeline.py`
- `tests/test_research_pipeline.py`
- `tests/test_research_governance_pipeline.py`
- `tests/test_research_governance_pipeline_cli_smoke.py`

### Verify Only

- `src/core/config.py`
- `src/research_pipeline.py`
- `src/governance_pipeline.py`

## 9. 测试迁移策略

### 9.1 `tests/test_research_pipeline.py`

从“测试脚本私有 `_load_candidate_specs()`”切换为：

- 测共享生产 helper
- 覆盖 YAML -> `candidate_specs` 的解析结果

这样测试目标会更准确，不再把共享逻辑绑死在某个脚本名下。

### 9.2 `tests/test_research_governance_pipeline.py`

保留现有 CLI 参数转发测试语义，但改为：

- 复用 `write_candidate_config(...)`
- 复用 `expected_candidate_specs(...)` 或 `assert_candidate_specs(...)`

### 9.3 `tests/test_research_governance_pipeline_cli_smoke.py`

去掉本地 `_write_candidate_config(...)`，改为：

- 直接使用测试 support helper 生成 YAML
- 需要时用共享断言 helper 对 `candidate_specs` 做校验

保留不变：

- smoke 的 artifact 断言
- blocked / fatal 行为断言
- 真实 CLI + service 测试边界

## 10. 实施顺序

建议按以下顺序落地：

1. 新增生产 helper 与测试 support helper
2. 先补/改共享 helper 的单测与现有 CLI 参数转发测试
3. 再让两个 CLI 切到共享生产 helper
4. 最后收敛 smoke 测试中的候选配置写入与 `candidate_specs` 断言

原因：

- 先有共享边界，再切换调用点，回归风险更低
- 先把测试固定住，后续重构不容易误伤 CLI 语义

## 11. 验证口径

本子项目至少应验证：

- 共享生产 helper 单测通过
- `run_research` 仍能正确解析外部 `candidate-config`
- `run_research_governance_pipeline` 仍能正确解析外部 `candidate-config`
- smoke 文件在收敛后仍全部通过

建议聚焦回归：

- `pytest tests/test_research_pipeline.py tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py -q`

## 12. 风险与控制

主要风险：

- 共享 helper 改动后，CLI 参数转发测试可能因为导入路径变化而失效
- 测试 support helper 过度设计，反而把简单样例封装得更难读
- smoke 若顺手抽太多 helper，容易把测试边界变模糊

控制策略：

- 只抽 `candidate-config` 写入/期望值，不抽 artifact 断言
- 生产 helper 保持薄层，不引入默认配置缓存或额外魔法
- 先做测试约束，再切换生产调用点
