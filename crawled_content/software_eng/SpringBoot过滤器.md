# SpringBoot过滤器

> 来源: https://liaoxuefeng.com/books/java/springboot/filter/index.html
> 爬取时间: 2026-06-25 13:29:47
> 学科: software_eng | 难度: 进阶
> 标签: SpringBoot, Filter, 过滤器, Web, 进阶

---


### Java教程


# 添加Filter


我们在Spring中已经学过了集成Filter，本质上就是通过代理，把Spring管理的Bean注册到Servlet容器中，不过步骤比较繁琐，需要配置web.xml。

`web.xml`

在Spring Boot中，添加一个Filter更简单了，可以做到零配置。我们来看看在Spring Boot中如何添加Filter。

`Filter`

Spring Boot会自动扫描所有的FilterRegistrationBean类型的Bean，然后，将它们返回的Filter自动注册到Servlet容器中，无需任何配置。

`FilterRegistrationBean`

我们还是以AuthFilter为例，首先编写一个AuthFilterRegistrationBean，它继承自FilterRegistrationBean：

`AuthFilter`
`AuthFilterRegistrationBean`

```
@ComponentpublicclassAuthFilterRegistrationBeanextendsFilterRegistrationBean<Filter> {@AutowiredUserService userService;@OverridepublicFiltergetFilter(){
        setOrder(10);returnnewAuthFilter();
    }classAuthFilterimplementsFilter{
        ...
    }
}
```


FilterRegistrationBean本身不是Filter，它实际上是Filter的工厂。Spring Boot会调用getFilter()，把返回的Filter注册到Servlet容器中。因为我们可以在FilterRegistrationBean中注入需要的资源，然后，在返回的AuthFilter中，这个内部类可以引用外部类的所有字段，自然也包括注入的UserService，所以，整个过程完全基于Spring的IoC容器完成。

`getFilter()`
`UserService`

再注意到AuthFilterRegistrationBean使用了setOrder(10)，因为Spring Boot支持给多个Filter排序，数字小的在前面，所以，多个Filter的顺序是可以固定的。

`setOrder(10)`

我们再编写一个ApiFilter，专门过滤/api/*这样的URL。首先编写一个ApiFilterRegistrationBean

`ApiFilter`
`/api/*`
`ApiFilterRegistrationBean`

```
@ComponentpublicclassApiFilterRegistrationBeanextendsFilterRegistrationBean<Filter> {@PostConstructpublicvoidinit(){
        setOrder(20);
        setFilter(newApiFilter());
        setUrlPatterns(List.of("/api/*"));
    }classApiFilterimplementsFilter{
        ...
    }
}
```


这个ApiFilterRegistrationBean和AuthFilterRegistrationBean又有所不同。因为我们要过滤URL，而不是针对所有URL生效，因此，在@PostConstruct方法中，通过setFilter()设置一个Filter实例后，再调用setUrlPatterns()传入要过滤的URL列表。

`@PostConstruct`
`setFilter()`
`setUrlPatterns()`

### 练习


在Spring Boot中添加Filter并指定顺序。


下载练习


### 小结


在Spring Boot中添加Filter更加方便，并且支持对多个Filter进行排序。

