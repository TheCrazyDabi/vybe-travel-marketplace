package com.vybe.app.data.api

import com.vybe.app.data.models.InterestList
import com.vybe.app.data.models.LoginBody
import com.vybe.app.data.models.OkResult
import com.vybe.app.data.models.PackageList
import com.vybe.app.data.models.PackageWrapper
import com.vybe.app.data.models.ProfileWrapper
import com.vybe.app.data.models.Recommended
import com.vybe.app.data.models.RegisterBody
import com.vybe.app.data.models.SwipeBody
import com.vybe.app.data.models.UserWrapper
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * 1:1 mapping of the Flask JSON API (see web README "API contract").
 * Auth is session-cookie based; the OkHttp client holds the cookie jar,
 * so no token plumbing is needed. 401/403 surfaced to ViewModels.
 */
interface VybeApi {
    // auth
    @POST("api/auth/register")
    suspend fun register(@Body body: RegisterBody): Response<UserWrapper>

    @POST("api/auth/login")
    suspend fun login(@Body body: LoginBody): Response<UserWrapper>

    @POST("api/auth/logout")
    suspend fun logout(): Response<OkResult>

    // traveler profile + preferences
    @GET("api/profile")
    suspend fun getProfile(): Response<ProfileWrapper>

    @PUT("api/profile")
    suspend fun updateProfile(@Body fields: Map<String, @JvmSuppressWildcards Any?>): Response<ProfileWrapper>

    @POST("api/preferences")
    suspend fun savePreferences(@Body fields: Map<String, @JvmSuppressWildcards Any?>): Response<ProfileWrapper>

    // packages + discovery
    @GET("api/packages")
    suspend fun packages(): Response<PackageList>

    @GET("api/packages/{id}")
    suspend fun packageDetail(@Path("id") id: Int): Response<PackageWrapper>

    @GET("api/packages/recommended")
    suspend fun recommended(
        @Query("max_price") maxPrice: Int? = null,
        @Query("destination") destination: String? = null,
        @Query("min_duration") minDuration: Int? = null,
        @Query("min_score") minScore: Int? = null
    ): Response<Recommended>

    @POST("api/packages/{id}/swipe")
    suspend fun swipe(@Path("id") id: Int, @Body body: SwipeBody): Response<OkResult>

    @POST("api/packages/{id}/like")
    suspend fun like(@Path("id") id: Int): Response<OkResult>

    @DELETE("api/packages/{id}/like")
    suspend fun unlike(@Path("id") id: Int): Response<OkResult>

    @POST("api/packages/{id}/save")
    suspend fun save(@Path("id") id: Int): Response<OkResult>

    @DELETE("api/packages/{id}/save")
    suspend fun unsave(@Path("id") id: Int): Response<OkResult>

    @GET("api/interests")
    suspend fun interests(@Query("action") action: String? = null): Response<InterestList>
}
