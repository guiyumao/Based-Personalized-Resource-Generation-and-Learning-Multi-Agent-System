package com.softwarecompetition.agentcore.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.StringHttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.util.ArrayList;
import java.util.List;

@Configuration
public class WebMvcConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(List<HttpMessageConverter<?>> converters) {
        List<MediaType> textPlain = List.of(MediaType.TEXT_PLAIN);

        for (HttpMessageConverter<?> converter : converters) {
            // 从StringHttpMessageConverter中移除text/plain，防止它抢在Jackson之前处理请求体
            if (converter instanceof StringHttpMessageConverter stringConverter) {
                List<MediaType> types = new ArrayList<>(stringConverter.getSupportedMediaTypes());
                types.removeAll(textPlain);
                stringConverter.setSupportedMediaTypes(types);
            }
            // 让Jackson也能处理text/plain类型的请求体（Knife4j调试界面不发application/json）
            if (converter instanceof MappingJackson2HttpMessageConverter jacksonConverter) {
                List<MediaType> types = new ArrayList<>(jacksonConverter.getSupportedMediaTypes());
                types.addAll(textPlain);
                jacksonConverter.setSupportedMediaTypes(types);
            }
        }
    }
}
