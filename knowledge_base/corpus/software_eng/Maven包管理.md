# Maven包管理

> 文档ID: e9960afc85a36b66f215
> 来源: https://www.runoob.com/maven/maven-tutorial.html
> 来源站点: www.runoob.com
> 来源类型: documentation
> 大学: 未标注
> 课程: Maven包管理
> 作者或机构: www.runoob.com
> 授权: source-terms
> 采集范围: public-page
> 语言: zh-CN
> 爬取时间: 2026-10-09 00:27:49
> 更新时间: 2026-10-09T03:10:30.426783+00:00
> 内容哈希: e1b16c5058ba9b9ff082706ed521692f2debc51127ba85c882d2605fbb3c530c
> 学科: software_eng | 难度: 基础
> 标签: Maven, 包管理, 依赖, pom.xml, 基础

---

# Maven 教程


Maven 翻译为"专家"、"内行"，是 Apache 下的一个纯 Java 开发的开源项目。基于项目对象模型（缩写：POM）概念，Maven利用一个中央信息片断能管理一个项目的构建、报告和文档等步骤。


Maven 是一个项目管理工具，可以对 Java 项目进行构建、依赖管理。


Maven 也可被用于构建和管理各种项目，例如 C#，Ruby，Scala 和其他语言编写的项目。Maven 曾是 Jakarta 项目的子项目，现为由 Apache 软件基金会主持的独立 Apache 项目。


## 阅读本教程前，您需要了解的知识


本教程主要针对初学者，帮助他们学习 Maven 工具的基本功能。完成本教程的学习后你的 Apache Maven 的专业知识将达到中等水平，随后你可以学习更高级的知识了。


阅读本教程，您需要有以下基础： Java 基础 。


## Maven 功能


Maven 能够帮助开发者完成以下工作：

- 构建
- 文档生成
- 报告
- 依赖
- SCMs
- 发布
- 分发
- 邮件列表

## Maven 特点

- 约定优于配置 ：提供标准化的项目结构和构建生命周期
- 依赖管理 ：自动处理项目依赖关系
- 插件体系 ：丰富的插件支持各种构建任务
- 多模块支持 ：简化大型项目的管理
- 中央仓库 ：访问全球共享的库资源

## 约定配置


Maven 提倡使用一个共同的标准目录结构，Maven 使用约定优于配置的原则，大家尽可能的遵守这样的目录结构。如下所示：


| 目录 | 目的 |
| --- | --- |
| ${basedir} | 存放pom.xml和所有的子目录 |
| ${basedir}/src/main/java | 项目的java源代码 |
| ${basedir}/src/main/resources | 项目的资源，比如说property文件，springmvc.xml |
| ${basedir}/src/test/java | 项目的测试类，比如说Junit代码 |
| ${basedir}/src/test/resources | 测试用的资源 |
| ${basedir}/src/main/webapp/WEB-INF | web应用文件目录，web项目的信息，比如存放web.xml、本地图片、jsp视图页面 |
| ${basedir}/target | 打包输出目录 |
| ${basedir}/target/classes | 编译输出目录 |
| ${basedir}/target/test-classes | 测试编译输出目录 |
| Test.java | Maven只会自动运行符合该命名规则的测试类 |
| ~/.m2/repository | Maven默认的本地仓库目录位置 |
