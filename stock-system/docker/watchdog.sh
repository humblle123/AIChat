#!/bin/bash
# Stock Picker Docker 看门狗
# 定期检测前端端口是否可访问，不通则自动重启容器
# 配合 macOS launchd 使用，实现休眠唤醒后自动恢复

PROJECT_DIR="/Volumes/N3000/AIChat/stock-system"
LOG_FILE="$PROJECT_DIR/docker/watchdog.log"
MAX_LOG_LINES=500

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"
}

# 截断日志
if [ -f "$LOG_FILE" ] && [ "$(wc -l < "$LOG_FILE")" -gt "$MAX_LOG_LINES" ]; then
    tail -200 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi

# 检查 Docker 是否在运行
if ! docker info > /dev/null 2>&1; then
    exit 0
fi

# 检查容器是否存在
if ! docker ps -a --format '{{.Names}}' | grep -q 'stock-picker-frontend'; then
    exit 0
fi

# 检测端口是否可访问
if ! curl -sf --max-time 5 http://localhost/ > /dev/null 2>&1; then
    log "端口不可达，正在重启容器..."
    cd "$PROJECT_DIR" && docker compose restart >> "$LOG_FILE" 2>&1
    if [ $? -eq 0 ]; then
        log "容器重启完成"
    else
        log "容器重启失败"
    fi
fi
