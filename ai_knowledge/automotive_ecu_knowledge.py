"""
🚗 معرفة كمبيوترات السيارات المتقدمة - Automotive ECU Knowledge
خبير في أنظمة التحكم الإلكترونية للسيارات (ECU)

المعرفة الشاملة:
- Engine Control Unit (ECU)
- Transmission Control Unit (TCU)
- ABS/ESP Control Units
- Body Control Module (BCM)
- OBD-II Protocols
- CAN Bus Systems
- Diagnostic Trouble Codes (DTC)
- ECU Programming & Tuning
- Sensor Systems
- Actuator Systems

شركة أزاد للأنظمة الذكية
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AutomotiveECUKnowledge:
    """
    خبير كمبيوترات السيارات والأنظمة الإلكترونية
    """
    
    def __init__(self):
        self.knowledge_base = self._build_comprehensive_knowledge()
        logger.info("🚗 Automotive ECU Knowledge initialized")
    
    def _build_comprehensive_knowledge(self) -> dict:
        """بناء قاعدة المعرفة الشاملة"""
        return {
            # ========== ECU - وحدة التحكم في المحرك ==========
            'engine_ecu': {
                'description': 'وحدة التحكم الإلكترونية في المحرك - الدماغ الرئيسي',
                'functions': {
                    'fuel_injection': {
                        'name': 'التحكم في الحقن',
                        'description': 'تحديد كمية الوقود ووقت الحقن',
                        'sensors': ['MAF', 'MAP', 'TPS', 'IAT', 'CTS', 'O2'],
                        'formula': 'Injection Time = (Base Pulse × Load Factor × Temp Correction) / Battery Voltage',
                        'common_issues': [
                            'حاقن مسدود → خشونة في المحرك',
                            'خلل في O2 sensor → استهلاك وقود عالي',
                            'ضغط وقود منخفض → فقدان قوة'
                        ]
                    },
                    'ignition_timing': {
                        'name': 'توقيت الإشعال',
                        'description': 'تحديد اللحظة المثلى لإشعال الشمعة',
                        'formula': 'Advance = Base Timing + (RPM Factor × Load Factor) - (Knock Correction)',
                        'range': '10-40 درجة قبل النقطة الميتة العليا (BTDC)',
                        'common_issues': [
                            'Knock Sensor خلل → إشعال متأخر → فقدان قوة',
                            'توقيت مبكر جداً → طرق في المحرك',
                            'توقيت متأخر → ارتفاع حرارة'
                        ]
                    },
                    'idle_control': {
                        'name': 'التحكم في الخمول',
                        'description': 'ضبط RPM عند الخمول',
                        'target': '600-900 RPM (حسب المحرك)',
                        'actuator': 'IAC (Idle Air Control) Valve',
                        'common_issues': [
                            'IAC متسخ → خمول غير مستقر',
                            'تسريب هواء → RPM عالي',
                            'TPS غير معاير → خمول منخفض'
                        ]
                    },
                    'vvt_control': {
                        'name': 'التحكم في توقيت الصمامات المتغير',
                        'description': 'VVT/VTEC - تغيير توقيت فتح الصمامات حسب الحمل',
                        'benefit': 'قوة أعلى + استهلاك أقل',
                        'solenoid': 'VVT Solenoid',
                        'common_issues': [
                            'VVT Solenoid خلل → P0010-P0014',
                            'زيت متسخ → تأخر في الاستجابة',
                            'سلسلة التوقيت مرتخية → صوت طقطقة'
                        ]
                    }
                },
                'sensors': {
                    'MAF': {
                        'name': 'Mass Air Flow Sensor',
                        'name_ar': 'حساس تدفق الهواء',
                        'function': 'قياس كمية الهواء الداخل للمحرك',
                        'range': '0-5V (Analog) أو Digital',
                        'formula': 'Air Mass (g/s) = MAF Voltage × Calibration Factor',
                        'testing': 'عند الخمول: 2-3 g/s، عند 2500 RPM: 15-25 g/s',
                        'common_codes': ['P0100', 'P0101', 'P0102', 'P0103', 'P0104'],
                        'symptoms': ['استهلاك وقود عالي', 'فقدان قوة', 'خشونة']
                    },
                    'MAP': {
                        'name': 'Manifold Absolute Pressure',
                        'name_ar': 'حساس ضغط المنفولد',
                        'function': 'قياس ضغط الهواء في مجمع السحب',
                        'range': '0-5V (0-100 kPa أو 0-14.5 PSI)',
                        'testing': 'عند الخمول: 0.5-1.5V (20-30 kPa)',
                        'formula': 'Pressure (kPa) = (Voltage × 20) - 4',
                        'common_codes': ['P0105', 'P0106', 'P0107', 'P0108']
                    },
                    'TPS': {
                        'name': 'Throttle Position Sensor',
                        'name_ar': 'حساس وضعية البوابة',
                        'function': 'قياس فتحة صمام الخانق (الثروتل)',
                        'range': '0.5V (مغلق) إلى 4.5V (مفتوح كلياً)',
                        'testing': 'يجب أن يتغير بشكل سلس بدون قفزات',
                        'calibration': 'يحتاج معايرة بعد التركيب',
                        'common_codes': ['P0120', 'P0121', 'P0122', 'P0123']
                    },
                    'O2': {
                        'name': 'Oxygen Sensor (Lambda)',
                        'name_ar': 'حساس الأكسجين',
                        'function': 'قياس نسبة الأكسجين في العادم',
                        'types': ['Narrow Band (0-1V)', 'Wide Band (0-5V)'],
                        'target': 'Lambda = 1.0 (14.7:1 air/fuel ratio)',
                        'testing': 'يجب أن يتأرجح بين 0.1-0.9V عند التسخين',
                        'common_codes': ['P0130-P0167'],
                        'lifespan': '100,000-150,000 كم'
                    },
                    'CTS': {
                        'name': 'Coolant Temperature Sensor',
                        'name_ar': 'حساس حرارة الماء',
                        'function': 'قياس درجة حرارة سائل التبريد',
                        'type': 'NTC (مقاومة سالبة)',
                        'testing': '20°C = 3kΩ، 80°C = 300Ω، 100°C = 180Ω',
                        'common_codes': ['P0115', 'P0116', 'P0117', 'P0118']
                    },
                    'IAT': {
                        'name': 'Intake Air Temperature',
                        'name_ar': 'حساس حرارة الهواء الداخل',
                        'function': 'قياس حرارة الهواء الداخل',
                        'purpose': 'تصحيح كثافة الهواء',
                        'common_codes': ['P0110', 'P0111', 'P0112', 'P0113']
                    },
                    'CKP': {
                        'name': 'Crankshaft Position Sensor',
                        'name_ar': 'حساس عمود الكرنك',
                        'function': 'تحديد موضع وسرعة دوران المحرك',
                        'type': 'Magnetic (Hall Effect أو Inductive)',
                        'critical': True,
                        'symptoms': 'لا يعمل المحرك إذا تعطل',
                        'common_codes': ['P0335', 'P0336', 'P0337', 'P0338']
                    },
                    'CMP': {
                        'name': 'Camshaft Position Sensor',
                        'name_ar': 'حساس عمود الكامات',
                        'function': 'تحديد موضع الصمامات',
                        'purpose': 'تزامن الحقن والإشعال',
                        'common_codes': ['P0340', 'P0341', 'P0342', 'P0343']
                    },
                    'Knock': {
                        'name': 'Knock Sensor',
                        'name_ar': 'حساس الطرق',
                        'function': 'كشف الطرق (Detonation) في المحرك',
                        'type': 'Piezoelectric',
                        'action': 'تأخير الإشعال عند الطرق',
                        'common_codes': ['P0325', 'P0326', 'P0327', 'P0328']
                    }
                }
            },
            
            # ========== OBD-II Codes ==========
            'obd2_codes': {
                'P0': 'Powertrain (المحرك ونقل الحركة)',
                'C0': 'Chassis (الشاسيه - ABS/ESP)',
                'B0': 'Body (الهيكل - BCM)',
                'U0': 'Network (شبكة الاتصال - CAN Bus)',
                'common_codes': {
                    'P0300': 'Random Misfire - عدم احتراق عشوائي',
                    'P0301-P0308': 'Misfire Cylinder 1-8 - عدم احتراق سلندر محدد',
                    'P0420': 'Catalyst Efficiency Below Threshold - كفاءة الكتلايزر منخفضة',
                    'P0171': 'System Too Lean Bank 1 - خليط فقير',
                    'P0172': 'System Too Rich Bank 1 - خليط غني',
                    'P0401': 'EGR Flow Insufficient - تدفق EGR غير كافي',
                    'P0505': 'Idle Control System Malfunction - خلل في نظام الخمول',
                    'P0128': 'Coolant Temp Below Thermostat Temp - حرارة منخفضة',
                    'P0134': 'O2 Sensor No Activity - حساس أكسجين لا يعمل',
                    'P0335': 'Crankshaft Position Sensor Circuit - دائرة حساس الكرنك',
                    'P0340': 'Camshaft Position Sensor Circuit - دائرة حساس الكامات',
                    'P0442': 'EVAP Small Leak - تسريب صغير في نظام البخار',
                    'P0455': 'EVAP Large Leak - تسريب كبير في نظام البخار',
                    'P0500': 'Vehicle Speed Sensor - حساس السرعة',
                    'P0562': 'System Voltage Low - جهد النظام منخفض',
                    'P0700': 'Transmission Control System - نظام التحكم في القير',
                    'P1000': 'OBD System Readiness Test - اختبار جاهزية النظام'
                }
            },
            
            # ========== CAN Bus ==========
            'can_bus': {
                'description': 'Controller Area Network - شبكة التحكم',
                'speed': {
                    'high_speed': '500 kbps (المحرك والأنظمة الحيوية)',
                    'medium_speed': '125 kbps (الراحة)',
                    'low_speed': '33.3 kbps (التشخيص)'
                },
                'structure': {
                    'wires': 'CAN High + CAN Low (2 أسلاك ملتوية)',
                    'voltage': 'CAN High: 3.5V، CAN Low: 1.5V (عند الإرسال)',
                    'termination': '120Ω في كل طرف',
                    'nodes': 'حتى 110 وحدة على نفس الشبكة'
                },
                'protocols': {
                    'CAN 2.0A': 'Standard 11-bit ID',
                    'CAN 2.0B': 'Extended 29-bit ID',
                    'CAN FD': 'Flexible Data Rate (أحدث)'
                },
                'diagnosis': {
                    'U0100': 'Lost Communication with ECU',
                    'U0101': 'Lost Communication with TCM',
                    'U0121': 'Lost Communication with ABS',
                    'U0155': 'Lost Communication with BCM'
                },
                'testing': [
                    'فحص الفولتية: CAN H = 2.5V عند الراحة',
                    'فحص المقاومة: 60Ω بين CAN H & CAN L',
                    'فحص الإشارة بالأوسلسكوب',
                    'استخدام CAN Bus Analyzer'
                ]
            },
            
            # ========== TCU/TCM - القير الأوتوماتيك ==========
            'transmission': {
                'description': 'Transmission Control Unit - وحدة التحكم في القير',
                'types': {
                    'conventional': 'قير عادي 4-10 سرعات',
                    'cvt': 'CVT - نسب متغيرة لا نهائية',
                    'dct': 'DCT/DSG - قير مزدوج',
                    'amt': 'AMT - يدوي آلي'
                },
                'sensors': {
                    'input_speed': 'سرعة عمود الإدخال',
                    'output_speed': 'سرعة عمود الإخراج',
                    'atf_temp': 'حرارة زيت القير',
                    'pressure': 'ضغط الزيت',
                    'gear_position': 'وضع الغيار'
                },
                'shift_logic': {
                    'parameters': ['السرعة', 'الحمل', 'TPS', 'حرارة الزيت'],
                    'modes': ['Eco', 'Normal', 'Sport', 'Manual'],
                    'protection': 'منع التعشيق عند RPM عالي'
                },
                'common_codes': {
                    'P0700': 'TCM Malfunction',
                    'P0715': 'Input Speed Sensor',
                    'P0720': 'Output Speed Sensor',
                    'P0731-P0734': 'Gear Ratio Incorrect',
                    'P0750-P0770': 'Shift Solenoid Malfunction'
                },
                'maintenance': [
                    'تغيير زيت القير: 60,000 كم',
                    'فحص الفلتر: كل تغيير زيت',
                    'معايرة التعلم: بعد إصلاحات كبيرة'
                ]
            },
            
            # ========== ABS/ESP ==========
            'abs_esp': {
                'description': 'Anti-lock Braking System & Electronic Stability Program',
                'abs': {
                    'function': 'منع انغلاق العجلات عند الفرملة',
                    'components': ['ECU', 'Hydraulic Unit', 'Wheel Speed Sensors'],
                    'operation': 'نبض الفرامل 15 مرة/ثانية',
                    'benefit': 'توقف أقصر + تحكم أفضل'
                },
                'esp': {
                    'function': 'منع الانزلاق والانقلاب',
                    'sensors': ['Yaw Rate', 'Lateral G', 'Steering Angle'],
                    'action': 'فرملة عجلات فردية + تقليل عزم المحرك'
                },
                'wheel_speed_sensors': {
                    'types': ['Active (Hall Effect)', 'Passive (Magnetic)'],
                    'location': 'عند كل عجلة',
                    'testing': '1000-2000 mV AC عند الدوران اليدوي'
                },
                'common_codes': {
                    'C0035-C0038': 'Left/Right Front/Rear Wheel Speed Sensor',
                    'C0040': 'ABS Motor Relay Circuit',
                    'C0045': 'Wheel Speed Sensor Frequency Error',
                    'C0050': 'Yaw Rate Sensor Malfunction'
                }
            },
            
            # ========== Body Control Module ==========
            'bcm': {
                'description': 'Body Control Module - وحدة التحكم في الهيكل',
                'functions': [
                    'الإضاءة الداخلية والخارجية',
                    'القفل المركزي',
                    'النوافذ الكهربائية',
                    'المساحات',
                    'نظام الإنذار',
                    'Immobilizer (منع الحركة)',
                    'Climate Control'
                ],
                'programming': {
                    'required_after': ['استبدال BCM', 'استبدال المفاتيح'],
                    'tools': ['Factory Scan Tool', 'Dealer-level Access'],
                    'data': 'VIN Programming + Key Learning'
                }
            },
            
            # ========== Diagnostic Tools ==========
            'diagnostic_tools': {
                'basic': {
                    'code_reader': 'قارئ أكواد بسيط - P codes فقط',
                    'cost': '50-200 درهم',
                    'limitation': 'قراءة وحذف أكواد فقط'
                },
                'advanced': {
                    'scan_tool': 'جهاز فحص متقدم',
                    'capabilities': [
                        'Live Data (بيانات حية)',
                        'Bi-Directional Control (تحكم)',
                        'Adaptations (تكييفات)',
                        'Coding (برمجة)',
                        'All Modules (جميع الوحدات)'
                    ],
                    'examples': ['Autel MaxiSys', 'Launch X431', 'Snap-on'],
                    'cost': '5,000-50,000 درهم'
                },
                'factory': {
                    'name': 'أجهزة الوكالة',
                    'examples': {
                        'Toyota': 'Techstream',
                        'Honda': 'HDS',
                        'BMW': 'ISTA',
                        'Mercedes': 'Xentry',
                        'VW/Audi': 'ODIS',
                        'Ford': 'IDS',
                        'GM': 'Tech2/MDI'
                    },
                    'access': 'يحتاج اشتراك'
                }
            },
            
            # ========== ECU Tuning ==========
            'ecu_tuning': {
                'description': 'تعديل برمجة ECU لزيادة الأداء',
                'methods': {
                    'chip_tuning': {
                        'method': 'قراءة وتعديل الملف من EEPROM',
                        'connection': 'OBD-II أو فتح ECU',
                        'gains': '+10-30% قوة وعزم'
                    },
                    'piggyback': {
                        'method': 'جهاز إضافي يعترض الإشارات',
                        'examples': ['Apexi SAFC', 'Unichip'],
                        'reversible': True
                    },
                    'standalone': {
                        'method': 'استبدال ECU بالكامل',
                        'examples': ['Haltech', 'AEM', 'MoTeC'],
                        'for': 'سيارات السباق'
                    }
                },
                'parameters': {
                    'fuel_map': 'جدول الوقود (AFR)',
                    'ignition_map': 'جدول الإشعال (Advance)',
                    'boost_pressure': 'ضغط التيربو (للمحركات التيربو)',
                    'rev_limiter': 'محدد الدوران',
                    'speed_limiter': 'محدد السرعة'
                },
                'risks': [
                    'ضمان الوكيل يلغى',
                    'استهلاك وقود أعلى',
                    'عمر المحرك قد يقل',
                    'قد يسبب أعطال إذا لم يتم بشكل صحيح'
                ],
                'recommendations': [
                    'استخدم ورشة محترفة',
                    'Dyno Tuning (على الداينو)',
                    'مراقبة AFR و Knock',
                    'استخدم بنزين عالي الأوكتان'
                ]
            },
            
            # ========== Modern Systems ==========
            'modern_systems': {
                'adas': {
                    'name': 'Advanced Driver Assistance Systems',
                    'features': [
                        'Adaptive Cruise Control (ACC)',
                        'Lane Keeping Assist (LKA)',
                        'Automatic Emergency Braking (AEB)',
                        'Blind Spot Monitoring (BSM)',
                        'Parking Sensors',
                        'Surround View Camera'
                    ],
                    'sensors': ['Radar', 'Camera', 'Ultrasonic', 'LiDAR'],
                    'calibration': 'يحتاج معايرة بعد تصليح الزجاج الأمامي'
                },
                'hybrid': {
                    'types': ['Mild Hybrid', 'Full Hybrid', 'Plug-in Hybrid'],
                    'components': [
                        'Electric Motor/Generator',
                        'High Voltage Battery (200-400V)',
                        'Power Control Unit (PCU)',
                        'DC-DC Converter',
                        'Regenerative Braking'
                    ],
                    'safety': '⚠️ HIGH VOLTAGE - خطر صعق كهربائي!'
                },
                'ev': {
                    'name': 'Electric Vehicle',
                    'components': [
                        'Battery Pack (400-800V)',
                        'Inverter',
                        'Electric Motor(s)',
                        'Onboard Charger',
                        'Battery Management System (BMS)',
                        'Thermal Management'
                    ],
                    'no_maintenance': ['زيت محرك', 'فلاتر', 'شمعات'],
                    'maintenance': ['فرامل', 'إطارات', 'تبريد', 'فحص كهربائي']
                }
            }
        }
    
    def get_ecu_info(self, ecu_type: str) -> dict:
        """الحصول على معلومات عن وحدة تحكم محددة"""
        return self.knowledge_base.get(ecu_type, {})
    
    def diagnose_code(self, dtc_code: str) -> dict:
        """تشخيص كود خطأ"""
        codes_db = self.knowledge_base.get('obd2_codes', {}).get('common_codes', {})
        
        if dtc_code in codes_db:
            return {
                'code': dtc_code,
                'description': codes_db[dtc_code],
                'found': True
            }
        
        # تحليل نوع الكود
        if dtc_code.startswith('P0'):
            category = 'Powertrain'
        elif dtc_code.startswith('C0'):
            category = 'Chassis'
        elif dtc_code.startswith('B0'):
            category = 'Body'
        elif dtc_code.startswith('U0'):
            category = 'Network'
        else:
            category = 'Unknown'
        
        return {
            'code': dtc_code,
            'category': category,
            'found': False,
            'recommendation': 'ابحث في قاعدة بيانات الكودات الخاصة بالصانع'
        }
    
    def get_sensor_info(self, sensor_name: str) -> dict:
        """معلومات عن حساس محدد"""
        sensors = self.knowledge_base.get('engine_ecu', {}).get('sensors', {})
        return sensors.get(sensor_name.upper(), {})


# ============================================================================
# Singleton
# ============================================================================

_automotive_ecu_instance = None

def get_automotive_ecu_knowledge():
    """الحصول على خبير كمبيوترات السيارات"""
    global _automotive_ecu_instance
    if _automotive_ecu_instance is None:
        _automotive_ecu_instance = AutomotiveECUKnowledge()
    return _automotive_ecu_instance

