import logging
import sys
import os
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
import threading

# 添加项目根目录到sys.path，使绝对导入可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 使用绝对导入替代相对导入
from manager.trader_manager import TraderManager


class HealthResponse(BaseModel):
    status: str
    time: Optional[str] = None


class TraderInfo(BaseModel):
    trader_id: str
    trader_name: str
    ai_model: str


class CompetitionData(BaseModel):
    traders: List[Dict[str, Any]]
    count: int


class Server:
    """HTTP API服务器"""
    
    def __init__(self, trader_manager: TraderManager, port: int = 8080):
        self.app = FastAPI(
            title="NOFX Trading API",
            description="AI驱动的加密货币交易系统API",
            version="1.0.0"
        )
        
        # 添加CORS中间件
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        self.trader_manager = trader_manager
        self.port = port
        
        # 设置路由
        self._setup_routes()
    
    def _setup_routes(self) -> None:
        """设置路由"""
        # 健康检查
        self.app.get("/health", response_model=HealthResponse)(self._handle_health)
        
        # API路由组
        # 竞赛总览
        self.app.get("/api/competition", response_model=CompetitionData)(self._handle_competition)
        
        # Trader列表
        self.app.get("/api/traders", response_model=List[TraderInfo])(self._handle_trader_list)
        
        # 指定trader的数据（使用query参数 ?trader_id=xxx）
        self.app.get("/api/status")(self._handle_status)
        self.app.get("/api/account")(self._handle_account)
        self.app.get("/api/positions")(self._handle_positions)
        self.app.get("/api/decisions")(self._handle_decisions)
        self.app.get("/api/decisions/latest")(self._handle_latest_decisions)
        self.app.get("/api/statistics")(self._handle_statistics)
        self.app.get("/api/equity-history")(self._handle_equity_history)
        self.app.get("/api/performance")(self._handle_performance)
    
    async def _handle_health(self):
        """健康检查"""
        return HealthResponse(status="ok", time=None)
    
    async def _handle_competition(self):
        """竞赛总览（对比所有trader）"""
        try:
            comparison = self.trader_manager.get_comparison_data()
            return comparison
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取对比数据失败: {e}")
    
    async def _handle_trader_list(self):
        """trader列表"""
        traders = self.trader_manager.get_all_traders()
        result = []
        
        for t in traders.values():
            result.append(TraderInfo(
                trader_id=t.get_id(),
                trader_name=t.get_name(),
                ai_model=t.get_ai_model()
            ))
        
        return result
    
    async def _handle_status(self, trader_id: Optional[str] = Query(None)):
        """系统状态"""
        try:
            if not trader_id:
                # 如果没有指定trader_id，返回第一个trader
                ids = self.trader_manager.get_trader_ids()
                if not ids:
                    raise HTTPException(status_code=400, detail="没有可用的trader")
                trader_id = ids[0]
            
            trader = self.trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"未找到trader {trader_id}")
            
            status = trader.get_status()
            return status
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    async def _handle_account(self, trader_id: Optional[str] = Query(None)):
        """账户信息"""
        try:
            if not trader_id:
                # 如果没有指定trader_id，返回第一个trader
                ids = self.trader_manager.get_trader_ids()
                if not ids:
                    raise HTTPException(status_code=400, detail="没有可用的trader")
                trader_id = ids[0]
            
            trader = self.trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"未找到trader {trader_id}")
            
            logging.info(f"📊 收到账户信息请求 [{trader.get_name()}]")
            try:
                account = trader.get_account_info()
                logging.info(f"✓ 返回账户信息 [{trader.get_name()}]: 净值={account['total_equity']:.2f}, 可用={account['available_balance']:.2f}, 盈亏={account['total_pnl']:.2f} ({account['total_pnl_pct']:.2f}%)")
                return account
            except Exception as e:
                logging.error(f"❌ 获取账户信息失败 [{trader.get_name()}]: {e}")
                raise HTTPException(status_code=500, detail=f"获取账户信息失败: {e}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    async def _handle_positions(self, trader_id: Optional[str] = Query(None)):
        """持仓列表"""
        try:
            if not trader_id:
                # 如果没有指定trader_id，返回第一个trader
                ids = self.trader_manager.get_trader_ids()
                if not ids:
                    raise HTTPException(status_code=400, detail="没有可用的trader")
                trader_id = ids[0]
            
            trader = self.trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"未找到trader {trader_id}")
            
            try:
                positions = trader.get_positions()
                return positions
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"获取持仓列表失败: {e}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    async def _handle_decisions(self, trader_id: Optional[str] = Query(None)):
        """决策日志列表"""
        try:
            if not trader_id:
                # 如果没有指定trader_id，返回第一个trader
                ids = self.trader_manager.get_trader_ids()
                if not ids:
                    raise HTTPException(status_code=400, detail="没有可用的trader")
                trader_id = ids[0]
            
            trader = self.trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"未找到trader {trader_id}")
            
            decision_logger = trader.get_decision_logger()
            if not decision_logger:
                raise HTTPException(status_code=500, detail="决策日志记录器未初始化")
            
            try:
                # 获取所有历史决策记录（无限制）
                records = decision_logger.get_latest_records(10000)
                return records
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"获取决策日志失败: {e}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    async def _handle_latest_decisions(self, trader_id: Optional[str] = Query(None)):
        """最新决策日志（最近5条，最新的在前）"""
        try:
            if not trader_id:
                # 如果没有指定trader_id，返回第一个trader
                ids = self.trader_manager.get_trader_ids()
                if not ids:
                    raise HTTPException(status_code=400, detail="没有可用的trader")
                trader_id = ids[0]
            
            trader = self.trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"未找到trader {trader_id}")
            
            decision_logger = trader.get_decision_logger()
            if not decision_logger:
                raise HTTPException(status_code=500, detail="决策日志记录器未初始化")
            
            try:
                records = decision_logger.get_latest_records(5)
                # 反转数组，让最新的在前面（用于列表显示）
                # GetLatestRecords返回的是从旧到新（用于图表），这里需要从新到旧
                records.reverse()
                return records
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"获取决策日志失败: {e}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    async def _handle_statistics(self, trader_id: Optional[str] = Query(None)):
        """统计信息"""
        try:
            if not trader_id:
                # 如果没有指定trader_id，返回第一个trader
                ids = self.trader_manager.get_trader_ids()
                if not ids:
                    raise HTTPException(status_code=400, detail="没有可用的trader")
                trader_id = ids[0]
            
            trader = self.trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"未找到trader {trader_id}")
            
            decision_logger = trader.get_decision_logger()
            if not decision_logger:
                raise HTTPException(status_code=500, detail="决策日志记录器未初始化")
            
            try:
                stats = decision_logger.get_statistics()
                return stats
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"获取统计信息失败: {e}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    async def _handle_equity_history(self, trader_id: Optional[str] = Query(None)):
        """收益率历史数据"""
        try:
            if not trader_id:
                # 如果没有指定trader_id，返回第一个trader
                ids = self.trader_manager.get_trader_ids()
                if not ids:
                    raise HTTPException(status_code=400, detail="没有可用的trader")
                trader_id = ids[0]
            
            trader = self.trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"未找到trader {trader_id}")
            
            decision_logger = trader.get_decision_logger()
            if not decision_logger:
                raise HTTPException(status_code=500, detail="决策日志记录器未初始化")
            
            try:
                # 获取尽可能多的历史数据（几天的数据）
                # 每3分钟一个周期：10000条 = 约20天的数据
                records = decision_logger.get_latest_records(10000)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"获取历史数据失败: {e}")
            
            # 构建收益率历史数据点
            history = []
            
            # 从AutoTrader获取初始余额（用于计算盈亏百分比）
            initial_balance = 0.0
            status = trader.get_status()
            if status and "initial_balance" in status:
                initial_balance = status["initial_balance"]
            
            # 如果无法从status获取，且有历史记录，则从第一条记录获取
            if initial_balance == 0 and records:
                # 第一条记录的equity作为初始余额
                if records and "account_state" in records[0]:
                    initial_balance = records[0]["account_state"].get("total_balance", 0)
            
            # 如果还是无法获取，返回错误
            if initial_balance == 0:
                raise HTTPException(status_code=500, detail="无法获取初始余额")
            
            for record in records:
                # TotalBalance字段实际存储的是TotalEquity
                total_equity = record.get("account_state", {}).get("total_balance", 0)
                # TotalUnrealizedProfit字段实际存储的是TotalPnL（相对初始余额）
                total_pnl = record.get("account_state", {}).get("total_unrealized_profit", 0)
                
                # 计算盈亏百分比
                total_pnl_pct = 0.0
                if initial_balance > 0:
                    total_pnl_pct = (total_pnl / initial_balance) * 100
                
                history.append({
                    "timestamp": record.get("timestamp", ""),
                    "total_equity": total_equity,
                    "available_balance": record.get("account_state", {}).get("available_balance", 0),
                    "total_pnl": total_pnl,
                    "total_pnl_pct": total_pnl_pct,
                    "position_count": record.get("account_state", {}).get("position_count", 0),
                    "margin_used_pct": record.get("account_state", {}).get("margin_used_pct", 0),
                    "cycle_number": record.get("cycle_number", 0),
                })
            
            return history
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    async def _handle_performance(self, trader_id: Optional[str] = Query(None)):
        """AI历史表现分析（用于展示AI学习和反思）"""
        try:
            if not trader_id:
                # 如果没有指定trader_id，返回第一个trader
                ids = self.trader_manager.get_trader_ids()
                if not ids:
                    raise HTTPException(status_code=400, detail="没有可用的trader")
                trader_id = ids[0]
            
            trader = self.trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"未找到trader {trader_id}")
            
            decision_logger = trader.get_decision_logger()
            if not decision_logger:
                raise HTTPException(status_code=500, detail="决策日志记录器未初始化")
            
            try:
                # 分析最近20个周期的交易表现
                performance = decision_logger.analyze_performance(20)
                return performance
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"分析历史表现失败: {e}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    def start(self) -> None:
        """启动服务器"""
        logging.info(f"🌐 API服务器启动在 http://localhost:{self.port}")
        logging.info("📊 API文档:")
        logging.info("  • GET  /api/competition      - 竞赛总览（对比所有trader）")
        logging.info("  • GET  /api/traders          - Trader列表")
        logging.info("  • GET  /api/status?trader_id=xxx     - 指定trader的系统状态")
        logging.info("  • GET  /api/account?trader_id=xxx    - 指定trader的账户信息")
        logging.info("  • GET  /api/positions?trader_id=xxx  - 指定trader的持仓列表")
        logging.info("  • GET  /api/decisions?trader_id=xxx  - 指定trader的决策日志")
        logging.info("  • GET  /api/decisions/latest?trader_id=xxx - 指定trader的最新决策")
        logging.info("  • GET  /api/statistics?trader_id=xxx - 指定trader的统计信息")
        logging.info("  • GET  /api/equity-history?trader_id=xxx - 指定trader的收益率历史数据")
        logging.info("  • GET  /api/performance?trader_id=xxx - 指定trader的AI学习表现分析")
        logging.info("  • GET  /health               - 健康检查")
        logging.info("  • 文档地址: http://localhost:%d/docs", self.port)
        logging.info("  • Redoc地址: http://localhost:%d/redoc", self.port)
        logging.info("")
        
        # 使用uvicorn.run启动服务器
        uvicorn.run(self.app, host="0.0.0.0", port=self.port)