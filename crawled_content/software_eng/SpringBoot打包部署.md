# SpringBoot打包部署

> 来源: https://liaoxuefeng.com/books/java/springboot/package/index.html
> 爬取时间: 2026-06-25 13:29:38
> 学科: software_eng | 难度: 基础
> 标签: SpringBoot, Maven, 打包, 部署, 基础

---


### Java教程


# 打包Spring Boot应用


我们在Maven的使用插件一节中介绍了如何使用maven-shade-plugin打包一个可执行的jar包。在Spring Boot应用中，打包更加简单，因为Spring Boot自带一个更简单的spring-boot-maven-plugin插件用来打包，我们只需要在pom.xml中加入以下配置：

`maven-shade-plugin`
`spring-boot-maven-plugin`
`pom.xml`

```
<project...>...<build><plugins><plugin><groupId>org.springframework.boot</groupId><artifactId>spring-boot-maven-plugin</artifactId></plugin></plugins></build></project>
```


无需任何配置，Spring Boot的这款插件会自动定位应用程序的入口Class，我们执行以下Maven命令即可打包：


```
$ mvn clean package
```


以springboot-exec-jar项目为例，打包后我们在target目录下可以看到两个jar文件：

`springboot-exec-jar`
`target`

```
$ ls
classes
generated-sources
maven-archiver
maven-status
springboot-exec-jar-1.0-SNAPSHOT.jar
springboot-exec-jar-1.0-SNAPSHOT.jar.original
```


其中，springboot-exec-jar-1.0-SNAPSHOT.jar.original是Maven标准打包插件打的jar包，它只包含我们自己的Class，不包含依赖，而springboot-exec-jar-1.0-SNAPSHOT.jar是Spring Boot打包插件创建的包含依赖的jar，可以直接运行：

`springboot-exec-jar-1.0-SNAPSHOT.jar.original`
`springboot-exec-jar-1.0-SNAPSHOT.jar`

```
$ java -jar springboot-exec-jar-1.0-SNAPSHOT.jar
```


这样，部署一个Spring Boot应用就非常简单，无需预装任何服务器，只需要上传jar包即可。


在打包的时候，因为打包后的Spring Boot应用不会被修改，因此，默认情况下，spring-boot-devtools这个依赖不会被打包进去。但是要注意，使用早期的Spring Boot版本时，需要配置一下才能排除spring-boot-devtools这个依赖：

`spring-boot-devtools`

```
<plugin><groupId>org.springframework.boot</groupId><artifactId>spring-boot-maven-plugin</artifactId><configuration><excludeDevtools>true</excludeDevtools></configuration></plugin>
```


如果不喜欢默认的项目名+版本号作为文件名，可以加一个配置指定文件名：


```
<project...>...<build><finalName>awesome-app</finalName>...</build></project>
```


这样打包后的文件名就是awesome-app.jar。

`awesome-app.jar`

### 练习


使用Spring Boot插件打包可执行jar。


下载练习


### 小结


Spring Boot提供了一个Maven插件用于打包所有依赖到单一jar文件，此插件十分易用，无需配置。

