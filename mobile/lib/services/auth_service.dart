import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AuthService extends ChangeNotifier {
  String? _email;
  String? _token;  // Session token from login
  String? _subscriptionStatus;
  String? _apiTier;
  bool _isLoading = true;
  
  String? get email => _email;
  String? get token => _token;  // Session token
  String? get subscriptionStatus => _subscriptionStatus;
  String? get apiTier => _apiTier;
  bool get isLoading => _isLoading;
  bool get isLoggedIn => _email != null && _token != null;
  bool get hasWebAccess => _subscriptionStatus == 'active' || _subscriptionStatus == 'lifetime';
  bool get hasApiAccess => _apiTier != null && _apiTier != 'none';
  
  AuthService() {
    _loadSavedAuth();
  }
  
  Future<void> _loadSavedAuth() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _email = prefs.getString('email');
      _token = prefs.getString('token');
      _subscriptionStatus = prefs.getString('subscription_status');
      _apiTier = prefs.getString('api_tier');
    } catch (e) {
      // Ignore errors on load
    }
    _isLoading = false;
    notifyListeners();
  }
  
  Future<void> login({
    required String email,
    required String token,
    String? subscriptionStatus,
    String? apiTier,
  }) async {
    _email = email;
    _token = token;
    _subscriptionStatus = subscriptionStatus;
    _apiTier = apiTier;
    
    // Save to local storage
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('email', email);
    await prefs.setString('token', token);
    if (subscriptionStatus != null) {
      await prefs.setString('subscription_status', subscriptionStatus);
    }
    if (apiTier != null) {
      await prefs.setString('api_tier', apiTier);
    }
    
    notifyListeners();
  }
  
  Future<void> logout() async {
    _email = null;
    _token = null;
    _subscriptionStatus = null;
    _apiTier = null;
    
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('email');
    await prefs.remove('token');
    await prefs.remove('subscription_status');
    await prefs.remove('api_tier');
    
    notifyListeners();
  }
  
  Future<void> updateSubscription({
    String? subscriptionStatus,
    String? apiTier,
  }) async {
    if (subscriptionStatus != null) _subscriptionStatus = subscriptionStatus;
    if (apiTier != null) _apiTier = apiTier;
    
    final prefs = await SharedPreferences.getInstance();
    if (subscriptionStatus != null) {
      await prefs.setString('subscription_status', subscriptionStatus);
    }
    if (apiTier != null) {
      await prefs.setString('api_tier', apiTier);
    }
    
    notifyListeners();
  }
}
