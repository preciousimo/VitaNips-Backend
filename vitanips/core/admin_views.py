# vitanips/core/admin_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from doctors.models import Doctor, Appointment
from pharmacy.models import Pharmacy, MedicationOrder
from users.serializers import UserSerializer
from doctors.serializers import DoctorSerializer
from pharmacy.serializers import PharmacySerializer

User = get_user_model()


class AdminStatsView(APIView):
    """
    Get overall platform statistics for admin dashboard
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        # Get date ranges
        today = timezone.now().date()
        this_month_start = today.replace(day=1)
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)

        # User stats
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        new_users_this_month = User.objects.filter(
            created_at__gte=this_month_start
        ).count()
        
        # Doctor stats
        total_doctors = Doctor.objects.count()
        verified_doctors = Doctor.objects.filter(is_verified=True).count()
        pending_verification = Doctor.objects.filter(is_verified=False).count()
        
        # Pharmacy stats
        total_pharmacies = Pharmacy.objects.count()
        active_pharmacies = Pharmacy.objects.filter(is_active=True).count()
        
        # Appointment stats
        total_appointments = Appointment.objects.count()
        appointments_this_month = Appointment.objects.filter(
            date__gte=this_month_start
        ).count()
        appointments_today = Appointment.objects.filter(
            date=today
        ).count()
        
        # Order stats
        total_orders = MedicationOrder.objects.count()
        pending_orders = MedicationOrder.objects.filter(
            status='pending'
        ).count()
        
        stats = {
            'users': {
                'total': total_users,
                'active': active_users,
                'new_this_month': new_users_this_month,
                'inactive': total_users - active_users,
            },
            'doctors': {
                'total': total_doctors,
                'verified': verified_doctors,
                'pending_verification': pending_verification,
            },
            'pharmacies': {
                'total': total_pharmacies,
                'active': active_pharmacies,
                'inactive': total_pharmacies - active_pharmacies,
            },
            'appointments': {
                'total': total_appointments,
                'this_month': appointments_this_month,
                'today': appointments_today,
            },
            'orders': {
                'total': total_orders,
                'pending': pending_orders,
            }
        }
        
        return Response(stats, status=status.HTTP_200_OK)


class AdminUsersListView(APIView):
    """
    List all users with filtering and pagination
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        users = User.objects.all().order_by('-created_at')
        
        # Filtering
        role = request.query_params.get('role', None)
        is_active = request.query_params.get('is_active', None)
        search = request.query_params.get('search', None)
        
        if role == 'admin':
            users = users.filter(Q(is_staff=True) | Q(is_superuser=True))
        elif role == 'doctor':
            users = users.filter(doctor_profile__isnull=False)
        elif role == 'pharmacy':
            users = users.filter(is_pharmacy_staff=True)
        elif role == 'patient':
            users = users.filter(
                is_staff=False,
                is_pharmacy_staff=False,
                doctor_profile__isnull=True
            )
        
        if is_active is not None:
            users = users.filter(is_active=is_active.lower() == 'true')
        
        if search:
            users = users.filter(
                Q(email__icontains=search) |
                Q(username__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        
        serializer = UserSerializer(users, many=True)
        return Response({
            'count': users.count(),
            'results': serializer.data
        }, status=status.HTTP_200_OK)


class AdminUserDetailView(APIView):
    """
    Get, update, or delete a specific user
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            serializer = UserSerializer(user)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    def patch(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            
            # Allow updating specific admin fields
            allowed_fields = ['is_active', 'is_staff', 'is_superuser', 'is_pharmacy_staff']
            for field in allowed_fields:
                if field in request.data:
                    setattr(user, field, request.data[field])
            
            user.save()
            serializer = UserSerializer(user)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class AdminDoctorsListView(APIView):
    """
    List all doctors with verification status filtering
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        doctors = Doctor.objects.all().select_related('user').order_by('-created_at')
        
        # Filtering
        verification_status = request.query_params.get('verified', None)
        search = request.query_params.get('search', None)
        
        if verification_status is not None:
            doctors = doctors.filter(is_verified=verification_status.lower() == 'true')
        
        if search:
            doctors = doctors.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(user__email__icontains=search)
            )
        
        serializer = DoctorSerializer(doctors, many=True)
        return Response({
            'count': doctors.count(),
            'results': serializer.data
        }, status=status.HTTP_200_OK)


class AdminDoctorVerificationView(APIView):
    """
    Verify or reject doctor applications
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def patch(self, request, doctor_id):
        try:
            doctor = Doctor.objects.get(id=doctor_id)
            is_verified = request.data.get('is_verified', None)
            
            if is_verified is not None:
                doctor.is_verified = is_verified
                doctor.save()
                
                # You could send notification to doctor here
                
                return Response({
                    'message': f'Doctor {"verified" if is_verified else "unverified"} successfully',
                    'doctor': DoctorSerializer(doctor).data
                }, status=status.HTTP_200_OK)
            
            return Response(
                {'error': 'is_verified field is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Doctor.DoesNotExist:
            return Response(
                {'error': 'Doctor not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class AdminPharmaciesListView(APIView):
    """
    List all pharmacies
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        pharmacies = Pharmacy.objects.all().order_by('-created_at')
        
        # Filtering
        is_active = request.query_params.get('is_active', None)
        search = request.query_params.get('search', None)
        
        if is_active is not None:
            pharmacies = pharmacies.filter(is_active=is_active.lower() == 'true')
        
        if search:
            pharmacies = pharmacies.filter(
                Q(name__icontains=search) |
                Q(address__icontains=search) |
                Q(email__icontains=search)
            )
        
        serializer = PharmacySerializer(pharmacies, many=True)
        return Response({
            'count': pharmacies.count(),
            'results': serializer.data
        }, status=status.HTTP_200_OK)


class AdminPharmacyDetailView(APIView):
    """
    Update pharmacy status
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def patch(self, request, pharmacy_id):
        try:
            pharmacy = Pharmacy.objects.get(id=pharmacy_id)
            
            if 'is_active' in request.data:
                pharmacy.is_active = request.data['is_active']
                pharmacy.save()
            
            serializer = PharmacySerializer(pharmacy)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Pharmacy.DoesNotExist:
            return Response(
                {'error': 'Pharmacy not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class AdminAnalyticsView(APIView):
    """
    Get detailed analytics data for charts and reports
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        today = timezone.now().date()
        
        # User growth over last 12 months
        user_growth = []
        for i in range(12, 0, -1):
            month_date = today - timedelta(days=30 * i)
            month_start = month_date.replace(day=1)
            month_end = (month_start + timedelta(days=32)).replace(day=1)
            
            count = User.objects.filter(
                created_at__gte=month_start,
                created_at__lt=month_end
            ).count()
            
            user_growth.append({
                'month': month_start.strftime('%b %Y'),
                'count': count
            })
        
        # Appointments by status
        appointment_stats = Appointment.objects.values('status').annotate(
            count=Count('id')
        )
        
        # Top specialties
        top_specialties = Doctor.objects.values(
            'specialties__name'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:5]
        
        analytics = {
            'user_growth': user_growth,
            'appointments_by_status': list(appointment_stats),
            'top_specialties': list(top_specialties),
        }
        
        return Response(analytics, status=status.HTTP_200_OK)
