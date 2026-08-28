# Flint Chart MCP 使用约定

## 核心原则

后续在本项目中开发或调整 Streamlit 页面、生成数据可视化图表时，**统一优先使用 Flint Chart MCP 插件** (`flint`) 进行图表规格定义、校验与编译。

## 服务器信息

- **名称**: `flint`
- **URL**: `https://flint.data-formulator.ai/mcp`
- **核心工具 (Tools)**:
  - `list_chart_types`: 查询支持的图表类型与 channel 映射关系
  - `compile_chart`: 将语义化 Flint Chart Spec 编译为目标引擎 JSON (ECharts / Vega-Lite / Chart.js)
  - `validate_chart`: 校验 Flint Spec 合法性
  - `list_themes`: 获取推荐视觉主题

## 工作流程

1. **确定图表类型**: 结合 SQL 查询出的 DataFrame 维度与度量，使用 `list_chart_types` 选择最匹配的图表形态（如 Grouped Bar Chart, Heatmap, Line Chart, Sunburst 等）。
2. **校验与编译**: 构造 `ChartAssemblyInput`，调用 `compile_chart` 编译出标准的 ECharts / Vega-Lite 节点 JSON。
3. **Streamlit 落地**:
   - 若编译目标为 Vega-Lite：直接使用 `st.vega_lite_chart(df, vega_spec)`
   - 若编译目标为 ECharts：通过 `streamlit_echarts` 渲染 `st_echarts(options)`
