from astrbot.api.event import filter, AstrMessageEvent, EventMessageType
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
import random
import time

@register("group_verification", "Your Name", "进群验证插件，自动发送验证码并验证新成员", "1.0.0", "https://github.com/yourusername/astrbot_plugin_group_verification")
class GroupVerificationPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 存储待验证成员信息: {user_id: {"code": str, "timestamp": int, "timeout": int, "group_id": str}}
        self.pending_verification = {}
        logger.info("进群验证插件已初始化")

    @filter.event_message_type(EventMessageType.OTHER_MESSAGE)
    async def on_member_join(self, event: AstrMessageEvent):
        """监听成员加入事件"""
        try:
            # 获取原始消息对象
            raw_message = event.message_obj.raw_message
            
            # 检查是否为 QQ 平台的群成员增加事件
            if hasattr(raw_message, 'post_type') and raw_message.post_type == 'notice':
                if raw_message.notice_type == 'group_increase':
                    user_id = str(raw_message.user_id)
                    group_id = str(raw_message.group_id)
                    
                    # 生成验证码
                    code_length = self.config.get("code_length", 6)
                    code = ''.join(random.choices('0123456789', k=code_length))
                    
                    # 获取超时时间
                    timeout = self.config.get("timeout", 300)
                    
                    # 存储验证信息
                    self.pending_verification[user_id] = {
                        "code": code,
                        "timestamp": time.time(),
                        "timeout": timeout,
                        "group_id": group_id
                    }
                    
                    # 发送验证码私聊消息
                    message = f"欢迎加入群聊！请在 {timeout} 秒内发送验证码到群里完成验证：\n{code}\n\n注意：请直接发送验证码数字，不要发送其他内容。"
                    await self.context.send_message(f"qq:private:{user_id}", message)
                    
                    logger.info(f"新成员 {user_id} 加入群 {group_id}，已发送验证码 {code}")
                    
        except Exception as e:
            logger.error(f"处理成员加入事件时出错: {e}")

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """监听群消息，验证验证码"""
        try:
            user_id = event.message_obj.sender.user_id
            message_str = event.message_str.strip()
            group_id = event.message_obj.group_id
            
            # 检查用户是否在待验证列表中
            if user_id in self.pending_verification:
                verification_info = self.pending_verification[user_id]
                
                # 检查是否超时
                if time.time() - verification_info["timestamp"] > verification_info["timeout"]:
                    # 验证超时
                    await self.kick_member(user_id, group_id)
                    del self.pending_verification[user_id]
                    await event.plain_result(f"验证超时，已将 {event.message_obj.sender.nickname} 移出群聊")
                    logger.info(f"用户 {user_id} 验证超时，已踢出群 {group_id}")
                    return
                
                # 检查是否为验证码
                if message_str != verification_info["code"]:
                    # 不是验证码，撤回消息
                    await self.recall_message(event.message_obj.message_id, group_id)
                    # 发送提示消息
                    await self.context.send_message(f"qq:private:{user_id}", "请直接发送验证码数字，不要发送其他内容。")
                    logger.info(f"用户 {user_id} 发送了非验证码消息，已撤回")
                    return
                
                # 验证码正确
                await event.plain_result(f"欢迎 {event.message_obj.sender.nickname} 加入群聊！验证成功。")
                del self.pending_verification[user_id]
                logger.info(f"用户 {user_id} 验证成功，已加入群 {group_id}")
                
        except Exception as e:
            logger.error(f"处理群消息时出错: {e}")

    async def kick_member(self, user_id: str, group_id: str):
        """踢出群成员（针对 QQ 平台）"""
        try:
            # 获取平台实例
            platforms = self.context.platform_manager.get_insts()
            for platform in platforms:
                if platform.get_adapter_name() == "aiocqhttp":
                    # 调用 QQ 平台的踢出接口
                    await platform.call_api("set_group_kick", {
                        "group_id": int(group_id),
                        "user_id": int(user_id),
                        "reject_add_request": False
                    })
                    break
        except Exception as e:
            logger.error(f"踢出成员时出错: {e}")

    async def recall_message(self, message_id: str, group_id: str):
        """撤回消息（针对 QQ 平台）"""
        try:
            # 获取平台实例
            platforms = self.context.platform_manager.get_insts()
            for platform in platforms:
                if platform.get_adapter_name() == "aiocqhttp":
                    # 调用 QQ 平台的撤回接口
                    await platform.call_api("delete_msg", {
                        "message_id": int(message_id)
                    })
                    break
        except Exception as e:
            logger.error(f"撤回消息时出错: {e}")

    async def terminate(self):
        """插件被卸载时调用"""
        logger.info("进群验证插件已卸载")