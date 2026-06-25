# SpringBoot集成Redis

> 来源: https://liaoxuefeng.com/books/java/springboot/integration/redis/index.html
> 爬取时间: 2026-06-25 13:29:51
> 学科: software_eng | 难度: 进阶
> 标签: SpringBoot, Redis, 缓存, 集成, 进阶

---


### Java教程


# 访问Redis


在Spring Boot中，要访问Redis，可以直接引入spring-boot-starter-data-redis依赖，它实际上是Spring Data的一个子项目——Spring Data Redis，主要用到了这几个组件：

`spring-boot-starter-data-redis`
- Lettuce：一个基于Netty的高性能Redis客户端；
- RedisTemplate：一个类似于JdbcTemplate的接口，用于简化Redis的操作。

因为Spring Data Redis引入的依赖项很多，如果只是为了使用Redis，完全可以只引入Lettuce，剩下的操作都自己来完成。


本节我们稍微深入一下Redis的客户端，看看怎么一步一步把一个第三方组件引入到Spring Boot中。


首先，我们添加必要的几个依赖项：

- io.lettuce:lettuce-core
- org.apache.commons:commons-pool2

注意我们并未指定版本号，因为在spring-boot-starter-parent中已经把常用组件的版本号确定下来了。

`spring-boot-starter-parent`

第一步是在配置文件application.yml中添加Redis的相关配置：

`application.yml`

```
spring:redis:host:${REDIS_HOST:localhost}port:${REDIS_PORT:6379}password:${REDIS_PASSWORD:}ssl:${REDIS_SSL:false}database:${REDIS_DATABASE:0}
```


然后，通过RedisConfiguration来加载它：

`RedisConfiguration`

```
@ConfigurationProperties("spring.redis")publicclassRedisConfiguration{privateString host;privateintport;privateString password;privateintdatabase;// getters and setters...}
```


再编写一个@Bean方法来创建RedisClient，可以直接放在RedisConfiguration中：

`@Bean`
`RedisClient`

```
@ConfigurationProperties("spring.redis")publicclassRedisConfiguration{
    ...@BeanRedisClientredisClient(){RedisURIuri=RedisURI.Builder.redis(this.host,this.port)
                .withPassword(this.password)
                .withDatabase(this.database)
                .build();returnRedisClient.create(uri);
    }
}
```


在启动入口引入该配置：


```
@SpringBootApplication@Import(RedisConfiguration.class)// 加载Redis配置publicclassApplication{
    ...
}
```


注意：如果在RedisConfiguration中标注@Configuration，则可通过Spring Boot的自动扫描机制自动加载，否则，使用@Import手动加载。

`@Configuration`
`@Import`

紧接着，我们用一个RedisService来封装所有的Redis操作。基础代码如下：

`RedisService`

```
@ComponentpublicclassRedisService{@AutowiredRedisClient redisClient;

    GenericObjectPool<StatefulRedisConnection<String, String>> redisConnectionPool;@PostConstructpublicvoidinit(){
        GenericObjectPoolConfig<StatefulRedisConnection<String, String>> poolConfig =newGenericObjectPoolConfig<>();
        poolConfig.setMaxTotal(20);
        poolConfig.setMaxIdle(5);
        poolConfig.setTestOnReturn(true);
        poolConfig.setTestWhileIdle(true);this.redisConnectionPool = ConnectionPoolSupport.createGenericObjectPool(() -> redisClient.connect(), poolConfig);
    }@PreDestroypublicvoidshutdown(){this.redisConnectionPool.close();this.redisClient.shutdown();
    }
}
```


注意到上述代码引入了Commons Pool的一个对象池，用于缓存Redis连接。因为Lettuce本身是基于Netty的异步驱动，在异步访问时并不需要创建连接池，但基于Servlet模型的同步访问时，连接池是有必要的。连接池在@PostConstruct方法中初始化，在@PreDestroy方法中关闭。

`@PostConstruct`
`@PreDestroy`

下一步，是在RedisService中添加Redis访问方法。为了简化代码，我们仿照JdbcTemplate.execute(ConnectionCallback)方法，传入回调函数，可大幅减少样板代码。

`JdbcTemplate.execute(ConnectionCallback)`

首先定义回调函数接口SyncCommandCallback：

`SyncCommandCallback`

```
@FunctionalInterfacepublicinterfaceSyncCommandCallback<T> {// 在此操作Redis:TdoInConnection(RedisCommands<String, String> commands);
}
```


编写executeSync方法，在该方法中，获取Redis连接，利用callback操作Redis，最后释放连接，并返回操作结果：

`executeSync`

```
public<T> TexecuteSync(SyncCommandCallback<T> callback){try(StatefulRedisConnection<String, String> connection = redisConnectionPool.borrowObject()) {
        connection.setAutoFlushCommands(true);
        RedisCommands<String, String> commands = connection.sync();returncallback.doInConnection(commands);
    }catch(Exception e) {
        logger.warn("executeSync redis failed.", e);thrownewRuntimeException(e);
    }
}
```


有的童鞋觉得这样访问Redis的代码太复杂了，实际上我们可以针对常用操作把它封装一下，例如set和get命令：

`set`
`get`

```
publicStringset(String key, String value){returnexecuteSync(commands -> commands.set(key, value));
}publicStringget(String key){returnexecuteSync(commands -> commands.get(key));
}
```


类似的，hget和hset操作如下：

`hget`
`hset`

```
publicbooleanhset(String key, String field, String value){returnexecuteSync(commands -> commands.hset(key, field, value));
}publicStringhget(String key, String field){returnexecuteSync(commands -> commands.hget(key, field));
}publicMap<String, String>hgetall(String key){returnexecuteSync(commands -> commands.hgetall(key));
}
```


常用命令可以提供方法接口，如果要执行任意复杂的操作，就可以通过executeSync(SyncCommandCallback<T>)来完成。

`executeSync(SyncCommandCallback<T>)`

完成了RedisService后，我们就可以使用Redis了。例如，在UserController中，我们在Session中只存放登录用户的ID，用户信息存放到Redis，提供两个方法用于读写：

`UserController`

```
@ControllerpublicclassUserController{publicstaticfinalStringKEY_USER_ID="__userid__";publicstaticfinalStringKEY_USERS="__users__";@AutowiredObjectMapper objectMapper;@AutowiredRedisService redisService;// 把User写入Redis:privatevoidputUserIntoRedis(User user)throwsException {
        redisService.hset(KEY_USERS, user.getId().toString(), objectMapper.writeValueAsString(user));
    }// 从Redis读取User:privateUsergetUserFromRedis(HttpSession session)throwsException {Longid=(Long) session.getAttribute(KEY_USER_ID);if(id !=null) {Strings=redisService.hget(KEY_USERS, id.toString());if(s !=null) {returnobjectMapper.readValue(s, User.class);
            }
        }returnnull;
    }
    ...
}
```


用户登录成功后，把ID放入Session，把User实例放入Redis：

`User`

```
@PostMapping("/signin")publicModelAndViewdoSignin(@RequestParam("email")String email,@RequestParam("password")String password, HttpSession session)throwsException {try{Useruser=userService.signin(email, password);
        session.setAttribute(KEY_USER_ID, user.getId());
        putUserIntoRedis(user);
    }catch(RuntimeException e) {returnnewModelAndView("signin.html", Map.of("email", email,"error","Signin failed"));
    }returnnewModelAndView("redirect:/profile");
}
```


需要获取User时，从Redis取出：


```
@GetMapping("/profile")publicModelAndViewprofile(HttpSession session)throwsException {Useruser=getUserFromRedis(session);if(user ==null) {returnnewModelAndView("redirect:/signin");
    }returnnewModelAndView("profile.html", Map.of("user", user));
}
```


从Redis读写Java对象时，序列化和反序列化是应用程序的工作，上述代码使用JSON作为序列化方案，简单可靠。也可将相关序列化操作封装到RedisService中，这样可以提供更加通用的方法：


```
public<T> Tget(String key, Class<T> clazz){
    ...
}public<T> Tset(String key, T value){
    ...
}
```


### 练习


在Spring Boot中访问Redis。


下载练习


### 小结


Spring Boot默认使用Lettuce作为Redis客户端，同步使用时，应通过连接池提高效率。

