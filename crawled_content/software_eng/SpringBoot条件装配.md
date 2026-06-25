# SpringBoot条件装配

> 来源: https://liaoxuefeng.com/books/java/springboot/conditional/index.html
> 爬取时间: 2026-06-25 13:29:42
> 学科: software_eng | 难度: 进阶
> 标签: SpringBoot, Conditional, 条件装配, 进阶

---


### Java教程


# 使用Conditional


使用Profile能根据不同的Profile进行条件装配，但是Profile控制比较糙，如果想要精细控制，例如，配置本地存储，AWS存储和阿里云存储，将来很可能会增加Azure存储等，用Profile就很难实现。


Spring本身提供了条件装配@Conditional，但是要自己编写比较复杂的Condition来做判断，比较麻烦。Spring Boot则为我们准备好了几个非常有用的条件：

`@Conditional`
`Condition`
- @ConditionalOnProperty：如果有指定的配置，条件生效；
- @ConditionalOnBean：如果有指定的Bean，条件生效；
- @ConditionalOnMissingBean：如果没有指定的Bean，条件生效；
- @ConditionalOnMissingClass：如果没有指定的Class，条件生效；
- @ConditionalOnWebApplication：在Web环境中条件生效；
- @ConditionalOnExpression：根据表达式判断条件是否生效。

我们以最常用的@ConditionalOnProperty为例，把上一节的StorageService改写如下。首先，定义配置storage.type=xxx，用来判断条件，默认为local：

`@ConditionalOnProperty`
`StorageService`
`storage.type=xxx`
`local`

```
storage:type:${STORAGE_TYPE:local}
```


设定为local时，启用LocalStorageService：

`LocalStorageService`

```
@Component@ConditionalOnProperty(value = "storage.type", havingValue = "local", matchIfMissing = true)publicclassLocalStorageServiceimplementsStorageService{
    ...
}
```


设定为aws时，启用AwsStorageService：

`aws`
`AwsStorageService`

```
@Component@ConditionalOnProperty(value = "storage.type", havingValue = "aws")publicclassAwsStorageServiceimplementsStorageService{
    ...
}
```


设定为aliyun时，启用AliyunStorageService：

`aliyun`
`AliyunStorageService`

```
@Component@ConditionalOnProperty(value = "storage.type", havingValue = "aliyun")publicclassAliyunStorageServiceimplementsStorageService{
    ...
}
```


注意到LocalStorageService的注解，当指定配置为local，或者配置不存在，均启用LocalStorageService。


可见，Spring Boot提供的条件装配使得应用程序更加具有灵活性。


### 练习


使用Spring Boot提供的条件装配。


下载练习


### 小结


Spring Boot提供了几个非常有用的条件装配注解，可实现灵活的条件装配。

