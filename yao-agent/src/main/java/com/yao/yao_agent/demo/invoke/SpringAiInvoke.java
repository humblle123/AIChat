package com.yao.yao_agent.demo.invoke;


import jakarta.annotation.Resource;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class SpringAiInvoke implements CommandLineRunner{

    @Resource
    private ChatModel dashScopeChatModel;

    @Override
    public void run(String... args) throws Exception {
        String response = dashScopeChatModel.call("你好，我是小爱同学，很高兴认识你。");
        System.out.println(response);
    }
}