# Flutter Multi-Niche Implementation Guide (Updated)

## 📋 Overview

The backend now supports **multi-niche shops** with a specific "Primary Niche + Capabilities" structure. This guide shows you how to implement the new dashboard logic.

---

## 🔄 API Changes

### New Response Structure

The API now explicitly returns `primary_niche` and `capabilities` to match the dashboard spec.

#### Login / User Profile / Shop Detail Response:
```json
{
  "shop_niche": "barber",           // DEPRECATED
  "shop_niches": ["barber", "massage_therapist"], // Full list
  
  // 🔥 NEW FIELDS FOR DASHBOARD LOGIC:
  "primary_niche": "barber",        // Drives Hero section
  "capabilities": ["massage_therapist"] // Drives secondary sections
}
```

---

## 🛠️ Implementation Steps

### Step 1: Update Data Models

**User Model Update:**
```dart
class User {
  final int? shopId;
  final String? primaryNiche;      // NEW
  final List<String>? capabilities; // NEW
  
  User.fromJson(Map<String, dynamic> json)
      : shopId = json['shop_id'],
        primaryNiche = json['primary_niche'] ?? json['shop_niche'],
        capabilities = json['capabilities'] != null 
            ? List<String>.from(json['capabilities'])
            : [];
}
```

---

### Step 2: Dashboard Logic (The "Home" Screen)

**Requirement:**
> We have ONE Home dashboard screen per shop.
> The PRIMARY niche drives the default layout and "Hero" section.
> Capabilities add extra niche-specific tiles further down.

**Implementation:**

```dart
class HomeDashboard extends StatefulWidget {
  final String primaryNiche;
  final List<String> capabilities;
  
  const HomeDashboard({
    required this.primaryNiche, 
    required this.capabilities
  });

  @override
  _HomeDashboardState createState() => _HomeDashboardState();
}

class _HomeDashboardState extends State<HomeDashboard> {
  String activeFilter = 'All'; // 'All', or specific niche

  @override
  Widget build(BuildContext context) {
    // 1. Context Chips (Hero)
    final allNiches = [widget.primaryNiche, ...widget.capabilities];
    
    return Scaffold(
      body: CustomScrollView(
        slivers: [
          // Header with Chips
          SliverToBoxAdapter(
            child: _buildContextChips(allNiches),
          ),
          
          // Hero Section (Driven by Primary Niche)
          if (activeFilter == 'All' || activeFilter == widget.primaryNiche)
            _buildHeroSection(widget.primaryNiche),
            
          // Secondary Sections (Driven by Capabilities)
          ...widget.capabilities.map((niche) {
             if (activeFilter == 'All' || activeFilter == niche) {
               return _buildNicheSection(niche);
             }
             return SliverToBoxAdapter(child: SizedBox.shrink());
          }).toList(),
        ],
      ),
    );
  }
  
  Widget _buildContextChips(List<String> niches) {
    return Row(
      children: [
        FilterChip(label: Text('All'), selected: activeFilter == 'All', ...),
        ...niches.map((n) => FilterChip(
          label: Text(n), 
          selected: activeFilter == n,
          onSelected: (_) => setState(() => activeFilter = n),
        )),
      ],
    );
  }
}
```

---

### Step 3: Tile Registry

Map niche keys to specific tile components.

```dart
Widget _buildHeroSection(String niche) {
  switch (niche) {
    case 'barber':
      return BarberHeroTiles(); // Today's Appts, Revenue, etc.
    case 'tattoo_artist':
      return TattooHeroTiles(); // Active Projects, Design Requests
    default:
      return GenericHeroTiles();
  }
}

Widget _buildNicheSection(String niche) {
  switch (niche) {
    case 'massage_therapist':
      return MassageTiles(); // Treatment Tracker, Health Disclosures
    case 'esthetician':
      return EstheticianTiles();
    default:
      return SizedBox.shrink();
  }
}
```

---

## 🧪 Testing Checklist

### 1. Login Flow
- [ ] Login returns `primary_niche` and `capabilities`
- [ ] App stores these values

### 2. Dashboard Display
- [ ] "All" view shows Primary Hero + Capability sections
- [ ] Context chips filter/reorder sections
- [ ] Primary niche always determines the Hero section layout

---

## 🚀 Summary

**Key Changes:**
1. ✅ API now returns `primary_niche` and `capabilities` explicitly.
2. ✅ Dashboard is a **single screen** with sections.
3. ✅ **Primary Niche** = Hero Section.
4. ✅ **Capabilities** = Additional Sections below.
5. ✅ **Context Chips** = Filter/Sort mechanism (not routing).

**Migration Path:**
- Update `User` model to parse new fields.
- Refactor Dashboard to use the single-screen, multi-section approach.
