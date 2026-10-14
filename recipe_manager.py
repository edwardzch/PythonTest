# -*- coding: utf-8 -*-
"""
配方绑定管理模块 (Recipe Manager)
管理测试脚本、产品编码、转接线编码绑定关系及寿命管理联动。
"""

import os
import json
import logging
import threading
from typing import List, Dict, Optional
from utils.app_utils import get_app_base_path

RECIPE_FILE_NAME = "recipes.json"

class RecipeManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(RecipeManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.recipes_file_path = os.path.join(get_app_base_path(), RECIPE_FILE_NAME)
        self.recipes: List[Dict] = []
        self._load_recipes()
        self._initialized = True

    def _load_recipes(self):
        """从 JSON 文件加载配方列表"""
        if not os.path.exists(self.recipes_file_path):
            self.recipes = []
            self.save_recipes()
            return

        try:
            with open(self.recipes_file_path, 'r', encoding='utf-8') as f:
                self.recipes = json.load(f)
            logging.info(f"配方表加载成功，共 {len(self.recipes)} 条记录。")
        except Exception as e:
            logging.error(f"加载配方表失败: {e}", exc_info=True)
            self.recipes = []

    def save_recipes(self):
        """保存配方表到 JSON 文件"""
        try:
            with open(self.recipes_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.recipes, f, ensure_ascii=False, indent=4)
            logging.info("配方表保存成功。")
            return True
        except Exception as e:
            logging.error(f"保存配方表失败: {e}", exc_info=True)
            return False

    def get_all_recipes(self) -> List[Dict]:
        """获取所有配方列表"""
        return self.recipes

    def add_recipe(self, recipe_data: Dict) -> bool:
        """添加新配方"""
        # 确保基础字段
        if 'id' not in recipe_data or not recipe_data['id']:
            import uuid
            recipe_data['id'] = f"rec_{uuid.uuid4().hex[:8]}"
        
        # 补全缺省值
        recipe_data.setdefault('recipe_name', '')
        recipe_data.setdefault('sequence_path', '')
        recipe_data.setdefault('product_code', '')
        recipe_data.setdefault('adapter_cables', [])
        recipe_data.setdefault('enable_life_management', True)
        
        self.recipes.append(recipe_data)
        return self.save_recipes()

    def update_recipe(self, recipe_id: str, new_data: Dict) -> bool:
        """更新已有配方"""
        for i, item in enumerate(self.recipes):
            if item.get('id') == recipe_id:
                new_data['id'] = recipe_id
                self.recipes[i] = new_data
                return self.save_recipes()
        return False

    def delete_recipe(self, recipe_id: str) -> bool:
        """删除指定配方"""
        initial_count = len(self.recipes)
        self.recipes = [r for r in self.recipes if r.get('id') != recipe_id]
        if len(self.recipes) < initial_count:
            return self.save_recipes()
        return False

    def get_recipes_for_sequence(self, seq_path: str) -> List[Dict]:
        """获取所有关联指定脚本路径的配方列表"""
        if not seq_path:
            return []
        seq_filename = os.path.basename(seq_path).lower()
        seq_norm_path = os.path.normpath(seq_path).lower()

        matched = []
        for recipe in self.recipes:
            rec_seq = recipe.get('sequence_path', '').strip()
            if not rec_seq:
                continue
            rec_seq_filename = os.path.basename(rec_seq).lower()
            rec_seq_norm = os.path.normpath(rec_seq).lower()
            if seq_filename == rec_seq_filename or seq_norm_path == rec_seq_norm or rec_seq_filename in seq_filename:
                matched.append(recipe)
        return matched

    def find_matching_recipe(self, seq_path: str, product_sn: str = "") -> Optional[Dict]:
        """
        根据当前测试脚本路径和产品SN匹配对应的配方。
        严格比对产品编码 / SN 前缀。若所选脚本在配方表中要求特定的 product_code，
        而输入的 product_sn 不符合，则返回 None（严格拦截）。
        """
        matched_by_seq = self.get_recipes_for_sequence(seq_path)
        if not matched_by_seq:
            return None

        sn_clean = product_sn.strip().upper() if product_sn else ""

        # 1. 尝试匹配指定产品编码 / 示例条码的配方
        if sn_clean:
            for recipe in matched_by_seq:
                prod_code = recipe.get('product_code', '').strip().upper()
                sample_sn = recipe.get('sample_sn', '').strip().upper()

                if prod_code and (
                    sn_clean.startswith(prod_code) or 
                    prod_code in sn_clean or 
                    sn_clean in prod_code
                ):
                    return recipe

                if sample_sn and (
                    sn_clean == sample_sn or 
                    sample_sn.startswith(sn_clean) or 
                    sn_clean.startswith(sample_sn)
                ):
                    return recipe

        # 2. 如果产品SN未精准匹配，检查是否有未限定 product_code 的通用配方
        for recipe in matched_by_seq:
            if not recipe.get('product_code', '').strip() and not recipe.get('sample_sn', '').strip():
                return recipe

        # 3. 若该脚本配置的所有配方均指定了特定 product_code，而当前 SN 无法匹配其中任何一个，严禁盲目返回默认配方！
        return None


def get_recipe_manager() -> RecipeManager:
    """获取 RecipeManager 单例"""
    return RecipeManager()
