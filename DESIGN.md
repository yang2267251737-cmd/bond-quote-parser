---
name: 报价工作台
description: 蓝白核对工作表的现行界面规范
colors:
  ink: "#163b56"
  text: "#243d4e"
  muted: "#536c7c"
  ground: "#f2f6f8"
  surface: "#fff"
  line: "#c6d3dc"
  soft-line: "#e0e7ec"
  tint: "#e9f0f5"
  accent: "#116b67"
  accent-hover: "#075650"
  saved: "#fff3cf"
  submitted: "#e5f0ff"
  focus: "#167c8a"
  table-header: "#e5edf3"
  field-border: "#afc0cd"
  button-border: "#aebfcb"
  invalid-ground: "#fff0f0"
  modified-ground: "#eaf7f2"
typography:
  headline:
    fontFamily: '"Segoe UI", "Microsoft YaHei", system-ui, sans-serif'
    fontSize: "24px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0"
  title:
    fontFamily: '"Segoe UI", "Microsoft YaHei", system-ui, sans-serif'
    fontSize: "19px"
    fontWeight: 650
    lineHeight: 1.5
  subheading:
    fontFamily: '"Segoe UI", "Microsoft YaHei", system-ui, sans-serif'
    fontSize: "15px"
    fontWeight: 650
    lineHeight: 1.5
  body:
    fontFamily: '"Segoe UI", "Microsoft YaHei", system-ui, sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  table:
    fontFamily: '"Segoe UI", "Microsoft YaHei", system-ui, sans-serif'
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: '"Segoe UI", "Microsoft YaHei", system-ui, sans-serif'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  swatch: "2px"
  cell: "3px"
  field: "4px"
  container: "5px"
spacing:
  tight: "4px"
  inline: "7px"
  control-y: "8px"
  control-x: "10px"
  small: "12px"
  medium: "16px"
  group: "20px"
  section: "24px"
  page-x: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.container}"
    padding: "8px 14px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.container}"
    padding: "8px 14px"
  button-secondary-hover:
    backgroundColor: "{colors.tint}"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.container}"
    padding: "8px 14px"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.container}"
    padding: "5px 8px"
  field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.field}"
    padding: "8px 10px"
  paste-area:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.field}"
    padding: "14px 16px"
    height: "190px"
    width: "100%"
  cell-field:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    typography: "{typography.table}"
    rounded: "{rounded.cell}"
    padding: "5px 7px"
    width: "100%"
  cell-field-modified:
    backgroundColor: "{colors.modified-ground}"
  cell-field-invalid:
    backgroundColor: "{colors.invalid-ground}"
  workflow-saved:
    backgroundColor: "{colors.saved}"
    textColor: "{colors.text}"
  workflow-submitted:
    backgroundColor: "{colors.submitted}"
    textColor: "{colors.text}"
  source-action:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.container}"
    padding: "2px 7px"
  inspector:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.container}"
    padding: "20px 22px"
---

# Design System: 报价工作台

## Overview

**Creative North Star: "蓝白核对工作表"**

深蓝主栏、淡蓝灰工作底色和白色输入面形成清楚的操作层次。界面使用紧凑的系统字体、细边框与数字对齐，使用户能够连续扫描、修改与核对同一行字段。

操作区使用标准按钮、输入框、选择框和表格。颜色承担主操作、工作状态与复核提示；文字始终说明状态。原文入口与对应名称放在同一单元格，核对依据在独立区域展开。

**Key Characteristics:**

- 深蓝与蓝灰构成工作界面，青绿色标识主操作。
- 浅黄和浅蓝分别承载已保存未提交、已提交状态。
- 细边框、轻微圆角与紧凑数字列维持工作表密度。
- 表格自行滚动，核对入口保持逐行可追溯。

## Colors

配色以冷调蓝白为主，青绿色用于操作，浅黄、浅蓝与浅红用于有明确含义的状态。数值以上方 token 为准。

### Primary

- **操作青绿**（accent / accent-hover）：识别、保存等主按钮及其悬停状态；链接、勾选框和输入光标也使用这一色系。
- **焦点青蓝**（focus）：键盘可见焦点与正在编辑的表格字段边框。

### Secondary

- **保存浅黄**（saved）：整行已保存未提交底色及图例。
- **提交浅蓝**（submitted）：整行已提交底色及图例；状态由用户标记。
- **校验浅红**（invalid-ground）：有字段问题的输入面和错误消息底色。
- **修改浅绿**（modified-ground）：已手工修改的字段输入面。

### Neutral

- **主栏蓝黑**（ink）：标题栏底色、章节标题、表头及原文入口。
- **正文蓝灰**（text）：表单、表格及一般正文。
- **说明蓝灰**（muted）：辅助说明、汇总、图例说明与页脚。
- **工作底色**（ground）与 **输入白**（surface）：区分页面工作底和可操作内容面。
- **主边线**（line）与 **轻分隔线**（soft-line）：容器边界、设置区分隔和行分隔。
- **悬停蓝灰**（tint）：普通按钮的悬停底色。
- **表头浅蓝灰**（table-header）：常规表头与固定列表头的统一背景。
- **字段边线**（field-border）与 **按钮边线**（button-border）：标准控件在静止时的可见边界。

### Named Rules

**The State Pairing Rule.** 工作状态底色必须伴随明确文字；保留已保存未提交和已提交的图例，字段问题同时提供复核文字与可访问的无效状态。

## Typography

**Body Font:** Segoe UI，依次回退至 Microsoft YaHei、system-ui 与 sans-serif。标题和控件沿用同一字体栈，没有独立展示字体或外部字体资产。

**Character:** 字级克制，层次来自字号、字重和颜色。表格与计数使用等宽数字特性，数值字段右对齐。

### Hierarchy

- **Headline**：主栏标题使用 headline token；窄屏缩至（21px）。
- **Title**：章节标题使用 title token；窄屏缩至（18px）。
- **Subheading**：核对区域内部标题使用 subheading token；空状态标题单独使用（18px）。
- **Body**：页面正文和标准表单使用 body token；多行输入行高为（1.7）。
- **Table**：表格、行内字段及核对正文使用 table token；表头字重为（650）。核对原文行高为（1.85），保留换行并允许长内容换行。
- **Label**：辅助说明、复核入口、图例及页脚使用 label token。控件标签和标准按钮使用（600）字重，文字操作使用（500）。

### Named Rules

**The Numeric Alignment Rule.** 金额、价格和收益率输入右对齐；表格与字符计数启用 tabular-nums，让逐行比较依靠列对齐。

## Layout

页面容器和主栏内层的最大宽度为（1700px）。常规主内容留白为（24px 32px 28px），主栏内层为（20px 32px），内层最小高度为（76px）。常用控件间距和组间距由 spacing token 记录；区域间另有实际使用的（22px、28px）间隔。

公司设置为三列网格：公司、别名、设置开关；展开的识别口径使用三列字段加操作列。上方保留完整多行粘贴区，下方为结果操作、筛选、可编辑表格和图例。筛选控件可换行，本地批次选择在宽屏靠右。

表格容器横向和纵向自行滚动，常规最大高度为（570px），表头置顶。常规固定列为动作（92px）、代码（142px）、名称（174px）；偏移由前列宽度累加。名称单元格内的原文或复核按钮位于名称输入下方。补充字段由展开控件显示，保持原表格列结构。

- **宽屏（min-width: 1700px）**：主内容顶间距变为（28px），主栏上下留白变为（22px）。
- **中屏（max-width: 1050px）**：识别口径变为两列，公司和别名列保留最小宽度；批次选择取消自动左边距，结果操作可换行。
- **窄屏（max-width: 700px）**：主内容留白为（18px 16px 24px）；公司设置重排为公司加开关、别名独占下一行。粘贴框高（175px）、内边距（12px）；隐藏字符计数，结果标题与操作上下排列。批次选择独占一行；核对面板变为单列。表格最大高度为（520px），动作和代码分别固定为（82px、134px），名称列随表格滚动。

窄屏继续使用可横向滚动的表格，保留字段之间的列关系。页面自身不以缩小字号来容纳所有列。

## Elevation & Depth

界面使用底色、细边框与粘性定位表达层次，没有装饰性投影。被核对的行使用上下内嵌细线（inset 0 1px #597f98, inset 0 -1px #597f98）标识；这是选择状态，不作为容器抬升。表头与固定列通过明确的层级保持在滚动内容上方。

### Named Rules

**The Flat Surface Rule.** 工作面保持平整，以背景、边线和明确状态区分层次；行选择使用内嵌边线。

## Shapes

控件和容器采用轻微圆角，使用 rounded token 区分图例、表格字段、标准字段和容器。按钮、表格外框及核对面板使用相同容器圆角；表单与原文块使用字段圆角。表格保留直线行列边界，不把单元格分割为独立卡片。

## Components

### Buttons

标准按钮紧凑、边界明确，最小高度为（38px）。主按钮使用青绿实底，次按钮使用白底细边框，quiet 变体使用透明底；文字操作移除边框并降低字重，最小高度为（32px）。窄屏结果操作按钮最小高度为（35px）。

悬停改变背景和边框，按下改变背景；普通按钮禁用时使用灰蓝底色与 not-allowed 光标，主按钮具有独立的淡青灰禁用样式。背景与文字颜色过渡为（0.16s ease）。键盘可见焦点统一采用焦点色的（3px）轮廓和（2px）外偏移。

### Inputs / Fields

标准字段为白底细边框，最小高度为（38px）。多行粘贴框可垂直调整，默认高度及留白由 paste-area token 记录，最小高度为（165px）。复选框为（16px），使用操作色。

字段有真实标签或屏幕阅读器标签；表格字段的可访问名称包含行标识和字段名。数值字段使用 decimal 输入提示。行内输入默认透明背景、透明边框，最小高度为（33px）；悬停显出边线，聚焦显出焦点边框与白底。手工修改显示浅绿底与绿色下边线，校验问题显示浅红底、红色边框和 aria-invalid。

### Worktable and Workflow States

表头使用浅蓝灰面与较粗字重，行间采用轻分隔线。已保存未提交和已提交的整行底色分别来自 workflow token，工作状态选择框提供对应文字。图例采用小方块加文本。

表格为语义 table，包含隐藏 caption 和列 scope。滚动容器可聚焦，并以可访问名称说明横向滚动。无结果时在表格位置展示说明和虚构样例入口；有数据但筛选无匹配时显示一条明确的空结果文字。

保存与导出在无数据、原文或口径待应用、字段校验进行中或保存进行中时禁用。输入停止（550ms）后自动识别；手工修改结果后，原文或口径变化需显式重新识别。识别支持 Ctrl + Enter，界面提供操作提示。

### Source Review and Evidence Panel

原文入口位于名称字段下方，使用紧凑文字按钮；有复核事项时显示数量，改用棕色与点状下划线。候选收益率旁显示文字确认按钮与“含义待确认”说明。

核对面板是带边框的白色区域，常规为两列（1.15fr 1fr），列间距（30px）；窄屏切换单列。面板展示原文、复核事项、修改记录和字段依据，长内容允许换行。打开时将所选行标为选择状态，并以即时滚动移至面板；关闭后清除该选择状态。

### Feedback and Accessibility

普通反馈使用带边框的浅青色消息面，错误使用浅红消息面。状态与汇总通过 polite live region 宣读；错误使用 alert。设置开关维护 aria-expanded 和 aria-controls，补充字段开关维护 aria-pressed。隐藏区域使用 hidden，辅助文字采用屏幕阅读器可读的隐藏样式。

常规页面允许平滑滚动，按钮只过渡背景和文字颜色。prefers-reduced-motion: reduce 时取消平滑滚动与按钮过渡；核对面板定位本身始终使用即时滚动。

## Do's and Don'ts

### Do:

- **Do** 将工作状态文字与对应底色一起显示。
- **Do** 保持数字列右对齐和等宽数字特性。
- **Do** 将每行原文入口放在名称下方，保留复核事项数量。
- **Do** 给控件提供可访问名称，并保留可见焦点与错误状态。
- **Do** 让窄屏表格在自身容器中滚动，并遵守减动效偏好。

### Don't:

- **Don't** 仅通过颜色表示工作状态或校验问题。
- **Don't** 用装饰性投影替代既有边线与背景层次。
- **Don't** 在窄屏压缩全部数据列或把行拆成失去列对齐的卡片。
- **Don't** 将已提交的本地状态表现成外部交易系统已执行的确认。
