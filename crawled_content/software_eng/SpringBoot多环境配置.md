# SpringBoot多环境配置

> 来源: https://liaoxuefeng.com/books/java/springboot/profiles/index.html
> 爬取时间: 2026-06-25 13:29:40
> 学科: software_eng | 难度: 进阶
> 标签: SpringBoot, Profile, 配置, 环境, 进阶

---


### Java教程


# 使用Profiles


Profile本身是Spring提供的功能，我们在使用条件装配中已经讲到了，Profile表示一个环境的概念，如开发、测试和生产这3个环境：

- native
- test
- production

或者按git分支定义master、dev这些环境：

- master
- dev

在启动一个Spring应用程序的时候，可以传入一个或多个环境，例如：


```
-Dspring.profiles.active=test,master
```


大多数情况下，使用一个环境就足够了。


Spring Boot对Profiles的支持在于，可以在application.yml中为每个环境进行配置。下面是一个示例配置：

`application.yml`

```
spring:application:name:${APP_NAME:unnamed}datasource:url:jdbc:hsqldb:file:testdbusername:sapassword:dirver-class-name:org.hsqldb.jdbc.JDBCDriverhikari:auto-commit:falseconnection-timeout:3000validation-timeout:3000max-lifetime:60000maximum-pool-size:20minimum-idle:1pebble:suffix:cache:falseserver:port:${APP_PORT:8080}---spring:config:activate:on-profile:testserver:port:8000---spring:config:activate:on-profile:productionserver:port:80pebble:cache:true
```


注意到分隔符---，最前面的配置是默认配置，不需要指定Profile，后面的每段配置都必须以spring.config.activate.on-profile: xxx开头，表示一个Profile。上述配置默认使用8080端口，但是在test环境下，使用8000端口，在production环境下，使用80端口，并且启用Pebble的缓存。

`---`
`spring.config.activate.on-profile: xxx`
`test`
`8000`
`production`
`80`

如果我们不指定任何Profile，直接启动应用程序，那么Profile实际上就是default，可以从Spring Boot启动日志看出：

`default`

```
...
2022-11-25T11:10:34.006+08:00  INFO 13537 --- [           main] com.itranswarp.learnjava.Application     : No active profile set, falling back to 1 default profile: "default"
```


上述日志显示未设置Profile，使用默认的Profile为default。


要以test环境启动，可输入如下命令：


```
$ java -Dspring.profiles.active=test -jar springboot-profiles-1.0-SNAPSHOT.jar

...
2022-11-25T11:09:02.946+08:00  INFO 13510 --- [           main] com.itranswarp.learnjava.Application     : The following 1 profile is active: "test"
...
2022-11-25T11:09:05.124+08:00  INFO 13510 --- [           main] o.s.b.w.embedded.tomcat.TomcatWebServer  : Tomcat started on port(s): 8000 (http) with context path ''
...
```


从日志看到活动的Profile是test，Tomcat的监听端口是8000。


通过Profile可以实现一套代码在不同环境启用不同的配置和功能。假设我们需要一个存储服务，在本地开发时，直接使用文件存储即可，但是，在测试和生产环境，需要存储到云端如S3上，如何通过Profile实现该功能？


首先，我们要定义存储接口StorageService：

`StorageService`

```
publicinterfaceStorageService{// 根据URI打开InputStream:InputStreamopenInputStream(String uri)throwsIOException;// 根据扩展名+InputStream保存并返回URI:Stringstore(String extName, InputStream input)throwsIOException;
}
```


本地存储可通过LocalStorageService实现：

`LocalStorageService`

```
@Component@Profile("default")publicclassLocalStorageServiceimplementsStorageService{@Value("${storage.local:/var/static}")String localStorageRootDir;finalLoggerlogger=LoggerFactory.getLogger(getClass());privateFile localStorageRoot;@PostConstructpublicvoidinit(){
        logger.info("Intializing local storage with root dir: {}",this.localStorageRootDir);this.localStorageRoot =newFile(this.localStorageRootDir);
    }@OverridepublicInputStreamopenInputStream(String uri)throwsIOException {FiletargetFile=newFile(this.localStorageRoot, uri);returnnewBufferedInputStream(newFileInputStream(targetFile));
    }@OverridepublicStringstore(String extName, InputStream input)throwsIOException {StringfileName=UUID.randomUUID().toString() +"."+ extName;FiletargetFile=newFile(this.localStorageRoot, fileName);try(OutputStreamoutput=newBufferedOutputStream(newFileOutputStream(targetFile))) {
            input.transferTo(output);
        }returnfileName;
    }
}
```


而云端存储可通过CloudStorageService实现：

`CloudStorageService`

```
@Component@Profile("!default")publicclassCloudStorageServiceimplementsStorageService{@Value("${storage.cloud.bucket:}")String bucket;@Value("${storage.cloud.access-key:}")String accessKey;@Value("${storage.cloud.access-secret:}")String accessSecret;finalLoggerlogger=LoggerFactory.getLogger(getClass());@PostConstructpublicvoidinit(){//TODO:logger.info("Initializing cloud storage...");
    }@OverridepublicInputStreamopenInputStream(String uri)throwsIOException {//TODO:thrownewIOException("File not found: "+ uri);
    }@OverridepublicStringstore(String extName, InputStream input)throwsIOException {//TODO:thrownewIOException("Unable to access cloud storage.");
    }
}
```


注意到LocalStorageService使用了条件装配@Profile("default")，即默认启用LocalStorageService，而CloudStorageService使用了条件装配@Profile("!default")，即非default环境时，自动启用CloudStorageService。这样，一套代码，就实现了不同环境启用不同的配置。

`@Profile("default")`
`@Profile("!default")`

### 练习


使用Profile启动Spring Boot应用。


下载练习


### 小结


Spring Boot允许在一个配置文件中针对不同Profile进行配置；


Spring Boot在未指定Profile时默认为default。

