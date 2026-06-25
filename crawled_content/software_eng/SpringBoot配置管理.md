# SpringBoot配置管理

> 来源: https://liaoxuefeng.com/books/java/springboot/configuration/index.html
> 爬取时间: 2026-06-25 13:29:45
> 学科: software_eng | 难度: 基础
> 标签: SpringBoot, Configuration, 配置, 基础

---


### Java教程


# 加载配置文件


加载配置文件可以直接使用注解@Value，例如，我们定义了一个最大允许上传的文件大小配置：

`@Value`

```
storage:local:max-size:102400
```


在某个FileUploader里，需要获取该配置，可使用@Value注入：


```
@ComponentpublicclassFileUploader{@Value("${storage.local.max-size:102400}")intmaxSize;

    ...
}
```


在另一个UploadFilter中，因为要检查文件的MD5，同时也要检查输入流的大小，因此，也需要该配置：

`UploadFilter`

```
@ComponentpublicclassUploadFilterimplementsFilter{@Value("${storage.local.max-size:100000}")intmaxSize;

    ...
}
```


多次引用同一个@Value不但麻烦，而且@Value使用字符串，缺少编译器检查，容易造成多处引用不一致（例如，UploadFilter把缺省值误写为100000）。

`100000`

为了更好地管理配置，Spring Boot允许创建一个Bean，持有一组配置，并由Spring Boot自动注入。


假设我们在application.yml中添加了如下配置：

`application.yml`

```
storage:local:# 文件存储根目录:root-dir:${STORAGE_LOCAL_ROOT:/var/storage}# 最大文件大小，默认100K:max-size:${STORAGE_LOCAL_MAX_SIZE:102400}# 是否允许空文件:allow-empty:false# 允许的文件类型:allow-types:jpg,png,gif
```


可以首先定义一个Java Bean，持有该组配置：


```
publicclassStorageConfiguration{privateString rootDir;privateintmaxSize;privatebooleanallowEmpty;privateList<String> allowTypes;//TODO:getters and setters}
```


保证Java Bean的属性名称与配置一致即可。然后，我们添加两个注解：


```
@Configuration@ConfigurationProperties("storage.local")publicclassStorageConfiguration{
    ...
}
```


注意到@ConfigurationProperties("storage.local")表示将从配置项storage.local读取该项的所有子项配置，并且，@Configuration表示StorageConfiguration也是一个Spring管理的Bean，可直接注入到其他Bean中：

`@ConfigurationProperties("storage.local")`
`storage.local`
`@Configuration`
`StorageConfiguration`

```
@ComponentpublicclassStorageService{finalLoggerlogger=LoggerFactory.getLogger(getClass());@AutowiredStorageConfiguration storageConfig;@PostConstructpublicvoidinit(){
        logger.info("Load configuration: root-dir = {}", storageConfig.getRootDir());
        logger.info("Load configuration: max-size = {}", storageConfig.getMaxSize());
        logger.info("Load configuration: allowed-types = {}", storageConfig.getAllowTypes());
    }
}
```


这样一来，引入storage.local的相关配置就很容易了，因为只需要注入StorageConfiguration这个Bean，这样可以由编译器检查类型，无需编写重复的@Value注解。


### 练习


用Spring Boot加载配置文件。


下载练习


### 小结


Spring Boot提供了@ConfigurationProperties注解，可以非常方便地把一段配置加载到一个Bean中。

`@ConfigurationProperties`
