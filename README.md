# 石头剪刀布课堂淘汰赛系统

**石头剪刀布课堂淘汰赛系统**：一个基于 Flask 的局域网课堂互动小游戏。教师开启房间后，学生在手机/电脑上报名加入，系统自动两两配对，进行石头剪刀布单败淘汰赛，直到决出全场总冠军。全程在教师机局域网内运行，无需外网。

## 快速开始

### 方式一：Docker 部署（推荐）

项目已内置 `Dockerfile` 与 `docker-compose.yaml`，无需在宿主机安装 Python，一键启动。

#### 1. 前提条件

- 已安装 [Docker](https://www.docker.com/products/docker-desktop/)（含 Docker Compose 插件，Docker Desktop 默认自带）。

#### 2. 构建并启动

```bash
docker compose up -d --build
```

- 首次构建会自动拉取 `python:3.14-slim` 基础镜像并安装依赖，之后启动秒级完成。
- 启动后服务监听 `0.0.0.0:5000`，端口映射见 `docker-compose.yaml`。

#### 3. 访问

- 教师控制台：`http://<本机局域网IP>:5000/teacher`（页面内自动显示学生访问地址，可一键复制）
- 学生入口：`http://<本机局域网IP>:5000/`

> 学生需与教师机处于同一局域网，用手机/电脑浏览器打开学生入口即可报名。

#### 4. 常用命令

```bash
docker compose up -d            # 后台启动
docker compose logs -f          # 查看实时日志
docker compose restart          # 重启容器
docker compose down             # 停止并移除容器
docker compose down --volumes   # 停止并移除容器（含匿名卷）
```

#### 5. 重新部署（代码更新后）

```bash
docker compose up -d --build
```

#### 6. 自定义配置

- 修改端口：编辑 `docker-compose.yaml` 中 `ports` 的 `"5000:5000"`，例如改为 `"8080:5000"`。
- 容器设置了 `restart: unless-stopped`，开机/异常退出后会自动重启。
- Dockerfile 中以非 root 用户 `appuser` 运行，`EXPOSE 5000`。

### 方式二：直接运行（不使用 Docker）

```bash
pip install -r requirements.txt
python app.py
```

- 服务监听 `0.0.0.0:5000`
- Windows 下可直接运行 `run.bat`

---

## 技术栈

- 后端：Python + Flask（唯一依赖，见 `requirements.txt`）
- 前端：原生 HTML / CSS / JavaScript（模板内嵌样式与脚本，无构建工具）
- 数据存储：内存态（`app.py` 中的全局字典 `game`），无数据库

## 项目结构

```
Dockerfile           # Docker 镜像构建文件（python:3.14-slim）
docker-compose.yaml  # Docker Compose 编排（端口映射、自动重启）
.dockerignore        # 构建镜像时排除的文件（如 .venv）
app.py               # Flask 后端：游戏逻辑 + API 路由
templates/
  index.html         # 学生入口：报名/加入房间
  game.html          # 学生对战大屏：出拳、轮空、冠军、晋级树
  teacher.html       # 教师控制台：开启/开始/结束、实时看板
static/
  style.css          # 目前为空，样式内嵌在各模板中
  game.js            # 目前为空，脚本内嵌在各模板中
requirements.txt     # Flask>=3.0,<4.0
run.bat              # Windows 启动脚本（启动服务并打开教师控制台）
data/                # 空目录（当前未使用，预留）
```

## 页面与角色

| 路由 | 模板 | 角色 |
|------|------|------|
| `/` | index.html | 学生报名（输入姓名 → 加入） |
| `/game` | game.html | 学生对战页（出拳、查看晋级树） |
| `/teacher` | teacher.html | 教师控制台（重置房间、开始淘汰赛、实时监控） |

## API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/teacher/start` | 重置并开启新房间，清空全部对局状态 |
| POST | `/api/teacher/begin_match` | 锁定名单并开始淘汰赛，生成第 1 轮对阵 |
| POST | `/api/teacher/stop` | 强制结束比赛 |
| POST | `/api/join` | 学生报名，body: `{name}`，返回 `player_id` |
| GET | `/api/player/<player_id>` | 查询玩家状态、当前对局、晋级树 |
| POST | `/api/play` | 出拳，body: `{player_id, choice}` |
| GET | `/api/teacher/status` | 教师端全局状态（玩家、对局、晋级树） |

## 游戏规则与核心逻辑

- **单败淘汰**：胜者晋级、败者淘汰，直到只剩 1 人成为冠军（`create_next_round`）。
- **轮空（Bye）**：当晋级人数为奇数时，随机挑选一人轮空直接晋级；**严禁同一人连续两轮轮空**（`select_bye_player` 优先选择上一轮未轮空者）。
- **平局**：石头剪刀布相同时视为平局，双方重新出拳。
- **配对**：每轮晋级者随机洗牌后两两配对；若本轮只剩轮空者（`bye`），则直接进入下一轮。
- **并发**：所有状态读写使用 `threading.Lock` 保护；多个 `game.html` 客户端通过轮询 `/api/player/<id>` 同步状态（约 1.2s 间隔）。

## 状态机

玩家 `status` 取值：`waiting`（已报名）→ `playing`（对局中）→ `winner`（本轮晋级）→ `eliminated`（淘汰）；特殊态 `bye`（本轮轮空）、`champion`（总冠军）。

对局 `match.status` 取值：`waiting` → `finished`。

全局 `game` 关键字段：
- `started` / `finished`：房间是否开放 / 比赛是否结束
- `round`：当前轮次（0 表示未开赛）
- `players`：玩家字典（以 `player_id` 为 key）
- `matches`：当前轮对局列表；`all_matches`：历史全部对局
- `bye_records`：轮空记录；`current_winners`：晋级候选池
- `champion`：总冠军 player_id

## 前端约定

- 所有样式与脚本均内嵌在对应 HTML 模板中，`static/style.css` 与 `static/game.js` 当前为空文件（历史遗留，暂无用途）。
- 学生身份通过 `localStorage` 的 `rps_player_id` / `rps_player_name` 保存。
- 教师端与学生端均通过 `setInterval` 轮询刷新状态（教师 1.5s，学生 1.2s），晋级树支持缩放（0.5x~2.0x）。

## 注意事项

- 状态全部在内存中，**重启服务会丢失所有报名与对局数据**。
- 无鉴权：`/teacher` 和所有 API 均无密码保护，仅适合可信局域网内使用。
- 界面文案均为中文（班级课堂场景）。
