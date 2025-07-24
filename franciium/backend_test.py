#!/usr/bin/env python3
"""
Comprehensive Backend API Testing for Francium E-commerce
Tests all major API endpoints including authentication, products, cart, and admin features.
"""

import requests
import json
import sys
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = "https://158c20c3-c979-4267-9faa-afedc83cbb8f.preview.emergentagent.com/api"

class FranciumAPITester:
    def __init__(self):
        self.base_url = BACKEND_URL
        self.session = requests.Session()
        self.user_token = None
        self.admin_token = None
        self.test_results = []
        
    def log_test(self, test_name, success, message, response_data=None):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {message}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "message": message,
            "response_data": response_data,
            "timestamp": datetime.now().isoformat()
        })
    
    def test_health_check(self):
        """Test basic health check endpoint"""
        try:
            # Note: The backend doesn't have a root endpoint, testing /products instead
            response = self.session.get(f"{self.base_url}/products")
            if response.status_code == 200:
                self.log_test("Health Check", True, "API is accessible and responding")
                return True
            else:
                self.log_test("Health Check", False, f"API returned status {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Health Check", False, f"Connection failed: {str(e)}")
            return False
    
    def test_user_registration(self):
        """Test user registration"""
        try:
            user_data = {
                "email": "testuser@francium.com",
                "password": "testpass123",
                "full_name": "Test User",
                "phone": "+91-9876543210",
                "address": "123 Test Street, Test City"
            }
            
            response = self.session.post(f"{self.base_url}/auth/register", json=user_data)
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data and "user" in data:
                    self.user_token = data["access_token"]
                    self.log_test("User Registration", True, f"User registered successfully: {data['user']['email']}")
                    return True
                else:
                    self.log_test("User Registration", False, "Missing access_token or user in response")
                    return False
            else:
                error_msg = response.json().get("detail", "Unknown error") if response.content else f"Status {response.status_code}"
                self.log_test("User Registration", False, f"Registration failed: {error_msg}")
                return False
                
        except Exception as e:
            self.log_test("User Registration", False, f"Registration error: {str(e)}")
            return False
    
    def test_user_login(self):
        """Test user login"""
        try:
            login_data = {
                "email": "testuser@francium.com",
                "password": "testpass123"
            }
            
            response = self.session.post(f"{self.base_url}/auth/login", json=login_data)
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.user_token = data["access_token"]
                    self.log_test("User Login", True, f"Login successful for: {data['user']['email']}")
                    return True
                else:
                    self.log_test("User Login", False, "Missing access_token in response")
                    return False
            else:
                error_msg = response.json().get("detail", "Unknown error") if response.content else f"Status {response.status_code}"
                self.log_test("User Login", False, f"Login failed: {error_msg}")
                return False
                
        except Exception as e:
            self.log_test("User Login", False, f"Login error: {str(e)}")
            return False
    
    def test_admin_login(self):
        """Test admin login"""
        try:
            admin_data = {
                "email": "admin@francium.com",
                "password": "admin123"
            }
            
            response = self.session.post(f"{self.base_url}/auth/login", json=admin_data)
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data and data["user"]["role"] == "admin":
                    self.admin_token = data["access_token"]
                    self.log_test("Admin Login", True, f"Admin login successful: {data['user']['email']}")
                    return True
                else:
                    self.log_test("Admin Login", False, "Missing access_token or not admin role")
                    return False
            else:
                error_msg = response.json().get("detail", "Unknown error") if response.content else f"Status {response.status_code}"
                self.log_test("Admin Login", False, f"Admin login failed: {error_msg}")
                return False
                
        except Exception as e:
            self.log_test("Admin Login", False, f"Admin login error: {str(e)}")
            return False
    
    def test_get_products(self):
        """Test getting products list"""
        try:
            response = self.session.get(f"{self.base_url}/products")
            
            if response.status_code == 200:
                products = response.json()
                if isinstance(products, list) and len(products) > 0:
                    self.log_test("Get Products", True, f"Retrieved {len(products)} products successfully")
                    return True
                else:
                    self.log_test("Get Products", False, "No products found or invalid response format")
                    return False
            else:
                self.log_test("Get Products", False, f"Failed to get products: Status {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Get Products", False, f"Get products error: {str(e)}")
            return False
    
    def test_get_categories(self):
        """Test getting product categories"""
        try:
            response = self.session.get(f"{self.base_url}/categories")
            
            if response.status_code == 200:
                categories = response.json()
                if isinstance(categories, list) and len(categories) > 0:
                    self.log_test("Get Categories", True, f"Retrieved {len(categories)} categories successfully")
                    return True
                else:
                    self.log_test("Get Categories", False, "No categories found or invalid response format")
                    return False
            else:
                self.log_test("Get Categories", False, f"Failed to get categories: Status {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Get Categories", False, f"Get categories error: {str(e)}")
            return False
    
    def test_admin_stats(self):
        """Test admin dashboard statistics"""
        if not self.admin_token:
            self.log_test("Admin Stats", False, "No admin token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = self.session.get(f"{self.base_url}/admin/stats", headers=headers)
            
            if response.status_code == 200:
                stats = response.json()
                required_fields = ["total_products", "total_orders", "total_users", "total_revenue"]
                if all(field in stats for field in required_fields):
                    self.log_test("Admin Stats", True, f"Admin stats retrieved: {stats}")
                    return True
                else:
                    self.log_test("Admin Stats", False, f"Missing required fields in stats response")
                    return False
            else:
                error_msg = response.json().get("detail", "Unknown error") if response.content else f"Status {response.status_code}"
                self.log_test("Admin Stats", False, f"Failed to get admin stats: {error_msg}")
                return False
                
        except Exception as e:
            self.log_test("Admin Stats", False, f"Admin stats error: {str(e)}")
            return False
    
    def test_add_to_cart(self):
        """Test adding product to cart"""
        if not self.user_token:
            self.log_test("Add to Cart", False, "No user token available")
            return False
            
        try:
            # First get a product to add to cart
            products_response = self.session.get(f"{self.base_url}/products")
            if products_response.status_code != 200 or not products_response.json():
                self.log_test("Add to Cart", False, "No products available to add to cart")
                return False
                
            product = products_response.json()[0]  # Get first product
            
            cart_data = {
                "product_id": product["id"],
                "quantity": 2
            }
            
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = self.session.post(f"{self.base_url}/cart/add", json=cart_data, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if "message" in data and "cart" in data:
                    self.log_test("Add to Cart", True, f"Product added to cart successfully: {data['message']}")
                    return True
                else:
                    self.log_test("Add to Cart", False, "Invalid response format")
                    return False
            else:
                error_msg = response.json().get("detail", "Unknown error") if response.content else f"Status {response.status_code}"
                self.log_test("Add to Cart", False, f"Failed to add to cart: {error_msg}")
                return False
                
        except Exception as e:
            self.log_test("Add to Cart", False, f"Add to cart error: {str(e)}")
            return False
    
    def test_get_cart(self):
        """Test getting user's cart"""
        if not self.user_token:
            self.log_test("Get Cart", False, "No user token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = self.session.get(f"{self.base_url}/cart", headers=headers)
            
            if response.status_code == 200:
                cart = response.json()
                if "id" in cart and "user_id" in cart and "items" in cart:
                    self.log_test("Get Cart", True, f"Cart retrieved successfully with {len(cart['items'])} items")
                    return True
                else:
                    self.log_test("Get Cart", False, "Invalid cart response format")
                    return False
            else:
                error_msg = response.json().get("detail", "Unknown error") if response.content else f"Status {response.status_code}"
                self.log_test("Get Cart", False, f"Failed to get cart: {error_msg}")
                return False
                
        except Exception as e:
            self.log_test("Get Cart", False, f"Get cart error: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("=" * 60)
        print("FRANCIUM E-COMMERCE BACKEND API TESTING")
        print("=" * 60)
        
        # Test sequence
        tests = [
            ("Health Check", self.test_health_check),
            ("User Registration", self.test_user_registration),
            ("User Login", self.test_user_login),
            ("Admin Login", self.test_admin_login),
            ("Get Products", self.test_get_products),
            ("Get Categories", self.test_get_categories),
            ("Admin Stats", self.test_admin_stats),
            ("Add to Cart", self.test_add_to_cart),
            ("Get Cart", self.test_get_cart),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n--- Testing {test_name} ---")
            if test_func():
                passed += 1
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        if passed == total:
            print("\n🎉 ALL TESTS PASSED! Backend API is working correctly.")
        else:
            print(f"\n⚠️  {total - passed} tests failed. Check the details above.")
        
        return passed == total

if __name__ == "__main__":
    tester = FranciumAPITester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)