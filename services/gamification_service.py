from decimal import Decimal
from typing import Dict, List, Optional
from extensions import db
from utils.db_safety import atomic_transaction


class GamificationService:
    
    POINTS_CONFIG = {
        'sale_created': 10,
        'payment_collected': 5,
        'customer_added': 3,
        'product_added': 2,
        'supplier_added': 2,
        'large_sale': 20,
        'perfect_sale': 15,
        'fast_payment': 8
    }
    
    BADGES = {
        'newbie': {'points': 0, 'name_ar': 'مبتدئ', 'icon': '🌱'},
        'bronze': {'points': 100, 'name_ar': 'برونزي', 'icon': '🥉'},
        'silver': {'points': 500, 'name_ar': 'فضي', 'icon': '🥈'},
        'gold': {'points': 1000, 'name_ar': 'ذهبي', 'icon': '🥇'},
        'platinum': {'points': 5000, 'name_ar': 'بلاتيني', 'icon': '💎'},
        'legend': {'points': 10000, 'name_ar': 'أسطوري', 'icon': '👑'}
    }
    
    @staticmethod
    def award_points(user_id: int, action: str, metadata: Optional[Dict] = None) -> Dict:
        from models import User
        
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False, 'error': 'User not found'}
        
        points = GamificationService.POINTS_CONFIG.get(action, 0)
        
        if action == 'large_sale' and metadata:
            amount = metadata.get('amount', 0)
            if amount > 10000:
                points = 50
            elif amount > 5000:
                points = 30
        
        if not hasattr(user, 'points'):
            user.points = 0
        
        user.points = (user.points or 0) + points
        
        old_badge = GamificationService.get_user_badge(user.points - points)
        new_badge = GamificationService.get_user_badge(user.points)
        
        level_up = old_badge['name_ar'] != new_badge['name_ar']
        
        db.session.flush()

        
        return {
            'success': True,
            'points_awarded': points,
            'total_points': user.points,
            'badge': new_badge,
            'level_up': level_up
        }
    
    @staticmethod
    def get_user_badge(points: int) -> Dict:
        for badge_key in reversed(list(GamificationService.BADGES.keys())):
            badge = GamificationService.BADGES[badge_key]
            if points >= badge['points']:
                return {
                    'key': badge_key,
                    'name_ar': badge['name_ar'],
                    'icon': badge['icon'],
                    'min_points': badge['points']
                }
        return GamificationService.BADGES['newbie']
    
    @staticmethod
    def get_leaderboard(limit: int = 10) -> List[Dict]:
        from models import User
        from utils.tenanting import scoped_user_query

        users = scoped_user_query(active_only=True, exclude_owners=True).order_by(
            User.points.desc() if hasattr(User, 'points') else User.id
        ).limit(limit).all()
        
        leaderboard = []
        for idx, user in enumerate(users, 1):
            points = getattr(user, 'points', 0) or 0
            badge = GamificationService.get_user_badge(points)
            
            leaderboard.append({
                'rank': idx,
                'user_id': user.id,
                'username': user.username,
                'full_name': user.full_name_ar or user.full_name,
                'points': points,
                'badge': badge
            })
        
        return leaderboard
    
    @staticmethod
    def get_user_stats(user_id: int) -> Dict:
        from models import User, Sale
        
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False}
        
        points = getattr(user, 'points', 0) or 0
        badge = GamificationService.get_user_badge(points)
        
        total_sales = Sale.query.filter_by(seller_id=user_id).count()
        total_amount = db.session.query(
            db.func.sum(Sale.amount_aed)
        ).filter_by(seller_id=user_id, status='confirmed').scalar() or Decimal('0')
        
        next_badge = None
        for badge_key in GamificationService.BADGES.keys():
            if GamificationService.BADGES[badge_key]['points'] > points:
                next_badge = GamificationService.BADGES[badge_key]
                break
        
        return {
            'success': True,
            'points': points,
            'current_badge': badge,
            'next_badge': next_badge,
            'points_to_next': (next_badge['points'] - points) if next_badge else 0,
            'total_sales': total_sales,
            'total_amount': float(total_amount)
        }

