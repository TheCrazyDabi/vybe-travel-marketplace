package com.vybe.app.data.models

import com.google.gson.annotations.SerializedName

// Mirror the Flask to_dict() shapes (snake_case kept 1:1 with the backend).

data class User(
    val id: Int = 0,
    val name: String = "",
    val email: String = "",
    val role: String = "traveler",
    val status: String = "active",
    val age_range: String? = null,
    val created_at: String? = null,
    val dashboard: String? = null
)

data class OperatorInfo(
    val id: Int = 0,
    val company_name: String = "",
    val is_verified: Boolean = false,
    val status: String = ""
)

data class TravelPackage(
    val id: Int = 0,
    val title: String = "",
    val destination: String = "",
    val lat: Double? = null,
    val lng: Double? = null,
    val cover_image: String? = null,
    val short_desc: String? = null,
    val itinerary: String? = null,
    val price: Int = 0,
    val currency: String = "INR",
    val duration_days: Int = 1,
    val available_dates: String? = null,
    val group_size: String? = null,
    val included: List<String> = emptyList(),
    val excluded: List<String> = emptyList(),
    val accommodation: String? = null,
    val transportation: String? = null,
    val activities: List<String> = emptyList(),
    val region_tags: List<String> = emptyList(),
    val climate_tags: List<String> = emptyList(),
    val scenery_tags: List<String> = emptyList(),
    val interest_tags: List<String> = emptyList(),
    val mood_tags: List<String> = emptyList(),
    val cancellation_terms: String? = null,
    val is_active: Boolean = true,
    val availability_status: String? = null,
    val operator: OperatorInfo? = null,
    val match_score: Double? = null,
    val match_reasons: List<String> = emptyList(),
    val match_explanation: String? = null
)

data class TravelerProfile(
    val budget_max: Int? = null,
    val budget_per_person: Int? = null,
    val budget_flex_pct: Int? = null,
    val duration_days: Int? = null,
    val preferred_regions: List<String> = emptyList(),
    val preferred_destinations: List<String> = emptyList(),
    val destination_prefs: List<String> = emptyList(),
    val avoid_destinations: List<String> = emptyList(),
    val preferred_region_text: String? = null,
    val destination_text: String? = null,
    val preferred_climate: List<String> = emptyList(),
    val scenery: List<String> = emptyList(),
    val interests: List<String> = emptyList(),
    val activity_prefs: List<String> = emptyList(),
    val disliked_activities: List<String> = emptyList(),
    val group_type: String? = null,
    val group_size_pref: String? = null,
    val num_travellers: Int? = null,
    val current_mood: String? = null,
    val travel_moods: List<String> = emptyList(),
    val travel_pace: String? = null,
    val trip_desires: List<String> = emptyList(),
    val trip_mode: String? = null,
    val travel_style: String? = null,
    val itinerary_pref: String? = null,
    val priority: String? = null,
    val start_city: String? = null,
    val travel_start_date: String? = null,
    val travel_end_date: String? = null,
    val date_flexible: Boolean? = null,
    val accommodation_prefs: List<String> = emptyList(),
    val transport_prefs: List<String> = emptyList(),
    val accessibility_notes: String? = null,
    val dietary_notes: String? = null,
    val other_notes: String? = null,
    val ideal_trip_text: String? = null,
    val avoid: List<String> = emptyList(),
    val onboarding_completed: Boolean = false,
    val onboarding_step: Int = 1
) {
    /** Same required-field rule as the web Discover gate. */
    fun missingRequired(): List<String> {
        val missing = mutableListOf<String>()
        if (current_mood.isNullOrBlank() && travel_moods.isEmpty()) missing.add("travel mood")
        if (budget_per_person == null && budget_max == null) missing.add("budget per person")
        if (duration_days == null) missing.add("trip duration")
        val dest = preferred_destinations + destination_prefs + preferred_regions
        if (dest.none { it.isNotBlank() }) missing.add("destinations or regions")
        return missing
    }
}

data class Interest(
    val id: Int = 0,
    val package_id: Int = 0,
    val action: String = "",
    @SerializedName("package") val pkg: TravelPackage? = null
)

data class Quotation(
    val id: Int = 0,
    val enquiry_id: Int = 0,
    val price_per_person: Int = 0,
    val total_price: Int? = null,
    val message: String? = null,
    val status: String = ""
)

data class Enquiry(
    val id: Int = 0,
    val traveler_id: Int = 0,
    val package_id: Int = 0,
    val company_id: Int = 0,
    val status: String = "",
    val num_travellers: Int? = null,
    val travel_date: String? = null,
    val message: String? = null,
    val total_cost: Int? = null,
    val created_at: String? = null,
    val updated_at: String? = null,
    @SerializedName("package") val pkg: TravelPackage? = null,
    val quotations: List<Quotation> = emptyList(),
    val booking: Booking? = null
)

data class Booking(
    val id: Int = 0,
    val enquiry_id: Int = 0,
    val traveler_id: Int = 0,
    val package_id: Int = 0,
    val company_id: Int = 0,
    val status: String = "",
    val total_cost: Int? = null,
    val payment_status: String? = null,
    val created_at: String? = null,
    val confirmed_at: String? = null,
    @SerializedName("package") val pkg: TravelPackage? = null
)

data class ChatMessage(
    val id: Int = 0,
    val conversation_id: Int = 0,
    val sender_id: Int = 0,
    val body: String = "",
    val is_read: Boolean = false,
    val created_at: String? = null
)

data class Conversation(
    val id: Int = 0,
    val traveler_id: Int = 0,
    val company_id: Int = 0,
    val package_id: Int? = null,
    val status: String = "",
    val created_at: String? = null,
    val updated_at: String? = null,
    val messages: List<ChatMessage> = emptyList()
)

data class UserWrapper(val user: User)
data class ProfileWrapper(val user: User, val profile: TravelerProfile)
data class PackageList(val packages: List<TravelPackage>)
data class PackageWrapper(@SerializedName("package") val pkg: TravelPackage)
data class InterestList(val interests: List<Interest>)
data class Recommended(val packages: List<TravelPackage>, val prefs: TravelerProfile?)
data class EnquiryList(val enquiries: List<Enquiry>)
data class EnquiryWrapper(val enquiry: Enquiry)
data class BookingList(val bookings: List<Booking>)
data class ConversationList(val conversations: List<Conversation>)
data class ConversationWrapper(val conversation: Conversation)
data class MessageList(val messages: List<ChatMessage>)
data class MessageWrapper(val message: ChatMessage)
data class OkResult(val ok: Boolean = false)
data class LoginBody(val email: String, val password: String)
data class RegisterBody(val name: String, val email: String, val password: String, val role: String)
data class SwipeBody(val action: String)
data class MessageBody(val body: String)
