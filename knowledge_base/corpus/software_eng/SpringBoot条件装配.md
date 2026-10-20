# SpringBoot条件装配

> 文档ID: d6617cf8e91aad61e5ea
> 来源: https://liaoxuefeng.com/books/java/springboot/conditional/index.html
> 来源站点: liaoxuefeng.com
> 来源类型: documentation
> 大学: 未标注
> 课程: SpringBoot条件装配
> 作者或机构: liaoxuefeng.com
> 授权: source-terms
> 采集范围: public-page
> 语言: zh-CN
> 爬取时间: 2026-10-09 00:27:23
> 更新时间: 2026-10-09T03:10:30.188837+00:00
> 内容哈希: 9d2dd52c72cc3ae60908371949a4dd815a32ff97fb9c5eb1220f2dc5b7dcd638
> 学科: software_eng | 难度: 进阶
> 标签: SpringBoot, Conditional, 条件装配, 进阶

---

### Java教程


# 使用Conditional


使用Profile能根据不同的Profile进行条件装配，但是Profile控制比较糙，如果想要精细控制，例如，配置本地存储，AWS存储和阿里云存储，将来很可能会增加Azure存储等，用Profile就很难实现。


Spring本身提供了条件装配 @Conditional ，但是要自己编写比较复杂的 Condition 来做判断，比较麻烦。Spring Boot则为我们准备好了几个非常有用的条件：

- @ConditionalOnProperty：如果有指定的配置，条件生效；
- @ConditionalOnBean：如果有指定的Bean，条件生效；
- @ConditionalOnMissingBean：如果没有指定的Bean，条件生效；
- @ConditionalOnMissingClass：如果没有指定的Class，条件生效；
- @ConditionalOnWebApplication：在Web环境中条件生效；
- @ConditionalOnExpression：根据表达式判断条件是否生效。

我们以最常用的 @ConditionalOnProperty 为例，把上一节的 StorageService 改写如下。首先，定义配置 storage.type=xxx ，用来判断条件，默认为 local ：


```
storage:
type:
${STORAGE_TYPE:local}
```


设定为 local 时，启用 LocalStorageService ：


```
@Component
@ConditionalOnProperty(value = "storage.type", havingValue = "local", matchIfMissing = true)
public
class
LocalStorageService
implements
StorageService
{
    ...
}
```


设定为 aws 时，启用 AwsStorageService ：


```
@Component
@ConditionalOnProperty(value = "storage.type", havingValue = "aws")
public
class
AwsStorageService
implements
StorageService
{
    ...
}
```


设定为 aliyun 时，启用 AliyunStorageService ：


```
@Component
@ConditionalOnProperty(value = "storage.type", havingValue = "aliyun")
public
class
AliyunStorageService
implements
StorageService
{
    ...
}
```


注意到 LocalStorageService 的注解，当指定配置为 local ，或者配置不存在，均启用 LocalStorageService 。


可见，Spring Boot提供的条件装配使得应用程序更加具有灵活性。


### 练习


使用Spring Boot提供的条件装配。


下载练习


### 小结


Spring Boot提供了几个非常有用的条件装配注解，可实现灵活的条件装配。
