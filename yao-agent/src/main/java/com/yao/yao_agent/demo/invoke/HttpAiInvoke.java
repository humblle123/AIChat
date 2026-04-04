package com.yao.yao_agent.demo.invoke;

import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import cn.hutool.json.JSONUtil;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class HttpAiInvoke {

    public static void main(String[] args) {
        // 替换成你真实的 API Key
        String apiKey = TestApiKey.apiKey;
        if (apiKey == null || apiKey.trim().isEmpty()) {
            apiKey = "sk-你的DashScope实际ApiKey";
        }

        // ====================== 构建请求体 ======================
        // messages 数组
        List<Map<String, String>> messages = new ArrayList<>();

        // system 消息
        Map<String, String> systemMsg = new HashMap<>();
        systemMsg.put("role", "system");
        systemMsg.put("content", "You are a helpful assistant.");
        messages.add(systemMsg);

        // user 消息
        Map<String, String> userMsg = new HashMap<>();
        userMsg.put("role", "user");
        userMsg.put("content", "你是谁？");
        messages.add(userMsg);

        // input 对象
        Map<String, Object> input = new HashMap<>();
        input.put("messages", messages);

        // 整体 body
        Map<String, Object> body = new HashMap<>();
        body.put("model", "qwen-plus");
        body.put("input", input);

        // parameters
        Map<String, String> parameters = new HashMap<>();
        parameters.put("result_format", "message");
        body.put("parameters", parameters);

        // 转 JSON 字符串
        String jsonBody = JSONUtil.toJsonStr(body);

        // ====================== 发送请求 ======================
        HttpResponse response = HttpRequest
                .post("https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation")
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .body(jsonBody)
                .timeout(15000)           // 超时 15 秒，可根据需要调整
                .execute();

        // 输出结果
        System.out.println("HTTP 状态码: " + response.getStatus());
        System.out.println("响应内容:");
        System.out.println(response.body());
    }
}