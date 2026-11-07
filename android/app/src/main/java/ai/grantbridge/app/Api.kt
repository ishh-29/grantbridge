package ai.grantbridge.app

import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Interceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.*
import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

private val Context.sessionStore by preferencesDataStore(name = "grantbridge_session")
data class AuthUser(val id: String, val email: String, val display_name: String)
data class AuthResponse(val access_token: String, val token_type: String, val expires_at: String, val user: AuthUser)
data class UserProfile(val id: String, val email: String, val display_name: String, val created_at: String)

data class Org(val id: Int, val name: String, val org_type: String = "Nonprofit", val country: String = "", val mission: String = "", val registration_number: String = "", val operating_regions: String = "", val areas_of_operation: List<String> = emptyList(), val beneficiaries: String = "", val previous_projects: String = "", val previous_funding: String = "", val contact_email: String = "", val contact_phone: String = "", val completion: Int = 0)
data class Grant(val id: Int, val title: String, val funder: String, val amount: String, val deadline: String, val sector: String, val source_url: String, val is_sample: Boolean, val source_status: String = "sample", val requirements: List<String> = emptyList())
data class ApplicationRow(val id: Int, val organization_id: Int, val grant_id: Int, val status: String, val current_stage: String, val switch_status: String, val switch_room_id: String = "")
data class OrganizationMember(val id: Int, val user_id: String, val email: String, val display_name: String, val role: String, val joined_at: String)
data class TeamMessageRow(val id: Int, val sender_id: String, val sender_name: String, val content: String, val created_at: String)
data class EligibilityAssessment(val id: Int, val status: String, val matching_requirements: List<String>, val missing_requirements: List<String>, val disqualifying_conditions: List<String>, val evidence: List<String>, val required_documents: List<String>, val provenance: String, val created_at: String)
data class Section(val id: Int, val title: String, val content: String, val provenance: String)
data class BudgetItem(val id: Int, val category: String, val description: String, val amount_cents: Int?, val currency: String, val provenance: String, val approval_status: String)
data class Issue(val id: Int, val issue: String, val severity: String, val requirement: String, val evidence: String, val suggested_correction: String, val assigned_to: String, val revision_requested: Boolean, val resolved: Boolean)
data class Event(val id: Int, val actor: String, val event_type: String, val detail: String, val source: String, val created_at: String)
data class DocumentRow(val id: Int, val filename: String, val category: String, val content_type: String, val byte_size: Int, val text_extracted: Boolean, val created_at: String)
data class NotificationRow(val id: Int, val organization_id: Int, val application_id: Int?, val title: String, val body: String, val type: String, val due_at: String?, val read_at: String?, val created_at: String)
data class ApplicationDetail(val id: Int, val organization_id: Int, val grant_id: Int, val status: String, val current_stage: String, val switch_status: String, val switch_room_id: String, val submitted_at: String?, val award_amount_cents: Int?, val reporting_requirements: List<String>, val grant: Grant, val eligibility_assessments: List<EligibilityAssessment>, val documents: List<Map<String, Any>>, val approvals: List<Map<String, Any>>, val sections: List<Section>, val budget_items: List<BudgetItem>, val issues: List<Issue>, val events: List<Event>)
data class Approval(val approved: Boolean, val note: String = "")
data class EditSection(val content: String)
data class BudgetEdit(val amount_cents: Int, val currency: String, val approved: Boolean)
data class HumanMessage(val content: String, val recipient: String? = null)

interface GrantBridgeApi {
    @POST("v1/auth/register") suspend fun register(@Body body: Map<String, String>): AuthResponse
    @POST("v1/auth/login") suspend fun login(@Body body: Map<String, String>): AuthResponse
    @POST("v1/auth/logout") suspend fun logout(): Map<String, Boolean>
    @GET("v1/profile") suspend fun profile(): UserProfile
    @PATCH("v1/profile") suspend fun updateProfile(@Body body: Map<String, String>): UserProfile
    @GET("v1/organizations") suspend fun organizations(): List<Org>
    @POST("v1/organizations") suspend fun createOrganization(@Body body: Map<String, Any>): Org
    @PUT("v1/organizations/{orgId}") suspend fun updateOrganization(@Path("orgId") orgId: Int, @Body body: Map<String, Any>): Org
    @GET("v1/organizations/{orgId}/members") suspend fun members(@Path("orgId") orgId: Int): List<OrganizationMember>
    @GET("v1/organizations/{orgId}/team-messages") suspend fun teamMessages(@Path("orgId") orgId: Int): List<TeamMessageRow>
    @POST("v1/organizations/{orgId}/team-messages") suspend fun sendTeamMessage(@Path("orgId") orgId: Int, @Body body: Map<String, String>): TeamMessageRow
    @POST("v1/organizations/{orgId}/members") suspend fun addMember(@Path("orgId") orgId: Int, @Body body: Map<String, String>): OrganizationMember
    @PATCH("v1/organizations/{orgId}/members/{memberId}") suspend fun updateMemberRole(@Path("orgId") orgId: Int, @Path("memberId") memberId: Int, @Body body: Map<String, String>): Map<String, Any>
    @DELETE("v1/organizations/{orgId}/members/{memberId}") suspend fun removeMember(@Path("orgId") orgId: Int, @Path("memberId") memberId: Int): Map<String, Boolean>
    @GET("v1/grants") suspend fun grants(@Query("q") query: String = "", @Query("sector") sector: String = ""): List<Grant>
    @GET("v1/grants/{grantId}") suspend fun grant(@Path("grantId") grantId: Int): Grant
    @POST("v1/grants/import") suspend fun importGrant(@Body body: Map<String, Any>): Grant
    @POST("v1/demo/seed") suspend fun seedDemo(): Grant
    @POST("v1/organizations/{orgId}/applications") suspend fun startApplication(@Path("orgId") orgId: Int, @Query("grant_id") grantId: Int): ApplicationRow
    @GET("v1/organizations/{orgId}/applications") suspend fun applications(@Path("orgId") orgId: Int): List<ApplicationRow>
    @GET("v1/organizations/{orgId}/documents") suspend fun documents(@Path("orgId") orgId: Int): List<DocumentRow>
    @GET("v1/notifications") suspend fun notifications(): List<NotificationRow>
    @POST("v1/notifications/{id}/read") suspend fun markNotificationRead(@Path("id") id: Int): Map<String, Boolean>
    @PUT("v1/applications/{id}/tracking") suspend fun tracking(@Path("id") id: Int, @Body body: Map<String, Any>): ApplicationRow
    @GET("v1/applications/{id}") suspend fun application(@Path("id") id: Int): ApplicationDetail
    @PUT("v1/applications/{id}/sections/{sectionId}") suspend fun editSection(@Path("id") id: Int, @Path("sectionId") sectionId: Int, @Body body: EditSection): Section
    @PUT("v1/applications/{id}/budget-items/{itemId}") suspend fun editBudget(@Path("id") id: Int, @Path("itemId") itemId: Int, @Body body: BudgetEdit): Map<String, Any>
    @Multipart @POST("v1/applications/{id}/documents") suspend fun uploadDocument(@Path("id") id: Int, @Part file: MultipartBody.Part, @Part("category") category: okhttp3.RequestBody): Map<String, Any>
    @POST("v1/applications/{id}/issues/{issueId}/handoff") suspend fun handoffIssue(@Path("id") id: Int, @Path("issueId") issueId: Int): Map<String, Boolean>
    @POST("v1/applications/{id}/issues/{issueId}/resolve") suspend fun resolveIssue(@Path("id") id: Int, @Path("issueId") issueId: Int, @Body body: HumanMessage): Map<String, Boolean>
    @POST("v1/applications/{id}/approve") suspend fun approve(@Path("id") id: Int, @Body body: Approval): ApplicationRow
    @POST("v1/applications/{id}/messages") suspend fun message(@Path("id") id: Int, @Body body: HumanMessage): Map<String, Boolean>
}

object ApiFactory {
    // Local demo only. Replace token-based authentication and base URL before deployment.
    private val BASE_URL = BuildConfig.API_BASE_URL
    @Volatile var accessToken: String? = null
    private val client = OkHttpClient.Builder().addInterceptor(Interceptor { chain ->
        val builder = chain.request().newBuilder()
        accessToken?.let { builder.header("Authorization", "Bearer $it") }
        val request = builder.build()
        chain.proceed(request)
    }).build()
    val service: GrantBridgeApi = Retrofit.Builder().baseUrl(BASE_URL).client(client)
        .addConverterFactory(GsonConverterFactory.create())
        .build().create(GrantBridgeApi::class.java)

    private val tokenKey = stringPreferencesKey("access_token")
    private const val KEY_ALIAS = "grantbridge_session_key"
    private fun sessionKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setRandomizedEncryptionRequired(true)
            .build())
        return generator.generateKey()
    }
    private fun encryptToken(token: String): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, sessionKey())
        val encrypted = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        return Base64.encodeToString(cipher.iv + encrypted, Base64.NO_WRAP)
    }
    private fun decryptToken(value: String): String {
        val packed = Base64.decode(value, Base64.NO_WRAP)
        require(packed.size > 12) { "Invalid encrypted session" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, sessionKey(), GCMParameterSpec(128, packed.copyOfRange(0, 12)))
        return cipher.doFinal(packed.copyOfRange(12, packed.size)).toString(Charsets.UTF_8)
    }
    suspend fun saveToken(context: Context, token: String) {
        context.applicationContext.sessionStore.edit { it[tokenKey] = encryptToken(token) }
        accessToken = token
    }
    suspend fun restoreToken(context: Context): String? {
        val stored = context.applicationContext.sessionStore.data.first()[tokenKey]
        val token = stored?.let(::decryptToken)
        accessToken = token
        return token
    }
    suspend fun clearToken(context: Context) {
        context.applicationContext.sessionStore.edit { it.remove(tokenKey) }
        accessToken = null
    }
}
