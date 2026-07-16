from django.urls import path
from myapp import views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView # type: ignore

    

urlpatterns = [
    path('home/', views.home, name='home'),
    #api endpoints
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path('upload/', views.upload_images, name='upload'),
    path('result/', views.result_view, name='change_result'),
    path('run-spatial-join/', views.spatial_join_view, name='result'),
    path('download-excel/', views.download_excel, name='download_excel'),
    path('download-shapefile/', views.download_shapefile, name='download_shapefile'),
    
    # Chunked upload for large files
    path('processing-availability/', views.processing_availability, name='processing_availability'),
    path('upload-chunk/', views.upload_chunk, name='upload_chunk'),
    
    # Building Footprint Detection
    path('start-footprint-detection/', views.start_footprint_detection, name='start_footprint_detection'),
    path('footprint-status/<int:job_id>/', views.footprint_status, name='footprint_status'),
    path('get-footprint-image/', views.get_footprint_image, name='get_footprint_image'),
    
    path('api/signup/', views.signup_api),
    path('api/login/', views.login_api),
    path('api/logout/', views.logout_api),
    path("api/feedbacks/", views.AllFeedbackAPIView.as_view(), name="all-feedbacks"),
    path("api/excel-files/<int:pk>/feedback/", views.FeedbackAPIView.as_view(), name="excel-feedback"),
    # Retrieve, Update, Delete a feedback
    path("api/feedback/<int:pk>/", views.FeedbackDetailAPIView.as_view(), name="feedback-detail"),
    path('api/users/', views.UserListCreateAPIView.as_view(), name='user_list_create'),
    path('api/users/<int:pk>/', views.UserDetailAPIView.as_view(), name='user_detail'),
    path('api/excel-files/', views.list_excel_files, name='list_excel_files'),
    path('api/upload-desktop-results/', views.upload_desktop_results, name='upload_desktop_results'),
    path('feedback-dashboard/', views.feedback_dashboard_view, name='feedback_dashboard'),
    path('user-dashboard/', views.user_dashboard_view, name='user_dashboard'),
    path('admin-dashboard/', views.admin_dashboard_view, name='admin_dashboard'),
    path('feedback/<int:feedback_id>/', views.feedback_detail_view, name='feedback_detail'),
    path('view-excel/', views.view_excel_sheet, name='view_excel'),
    
    # API endpoints for result deletion
    path('api/change-results/<int:pk>/', views.ChangeResultDetailAPIView.as_view(), name='change_result_detail'),
    path('api/spatial-join-results/<int:pk>/', views.SpatialJoinResultDetailAPIView.as_view(), name='spatial_join_result_detail'),
    
    path('spatial-join/', views.spatial_join_view, name='spatial_join'),
    path('start-processing/', views.start_processing, name='start_processing'),
    path('task-status/<str:task_id>/', views.task_status, name='task_status'),

    
    
    path('', views.login_page),
    path('login/', views.login_page, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('signup/', views.signup_page),
    path(
            'footprint-status/<int:pk>/',
            views.footprint_status,
            name='footprint-status'
        ),
    
      
]
