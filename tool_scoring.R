library(synapser)
library(dplyr)
library(tidyr)

# Login to Synapse (you'll need to authenticate first)
synLogin()

# Function to count non-NA, non-empty values
count_filled <- function(x) {
  sum(!is.na(x) & x != "" & x != "NULL", na.rm = TRUE)
}

# Function to calculate completeness score for a tool
calculate_tool_score <- function(resource_data, observations_data) {

  score_breakdown <- list()
  total_score <- 0
  tool_type <- resource_data$resourceType

  # Availability (40 points)
  availability_score <- 0

  if (!is.na(tool_type) && tool_type == "biobank") {
    # For biobanks: biobankURL (40 points)
    if (!is.null(resource_data$biobankURL) && !is.na(resource_data$biobankURL) &&
        resource_data$biobankURL != "" && resource_data$biobankURL != "NULL") {
      availability_score <- 40
    }
    score_breakdown$biobank_url <- availability_score
  } else {
    # For other resource types: vendor/developer (20), RRID (10), DOI (10)

    # Vendor/developer: 20 points
    vendor_developer_score <- 0
    # Check if isDeveloper and institution is filled, or vendor info is filled, or developer info is filled
    has_developer_info <- (!is.null(resource_data$isDeveloper) && !is.na(resource_data$isDeveloper) &&
                           !is.null(resource_data$institution) && !is.na(resource_data$institution) &&
                           resource_data$institution != "" && resource_data$institution != "NULL")
    has_vendor_info <- (!is.null(resource_data$vendorName) && !is.na(resource_data$vendorName) &&
                        resource_data$vendorName != "" && resource_data$vendorName != "NULL")

    if (has_developer_info || has_vendor_info) {
      vendor_developer_score <- 20
    }
    score_breakdown$vendor_developer <- vendor_developer_score
    availability_score <- availability_score + vendor_developer_score

    # RRID: 10 points
    rrid_score <- 0
    if (!is.null(resource_data$rrid) && !is.na(resource_data$rrid) &&
        resource_data$rrid != "" && resource_data$rrid != "NULL") {
      rrid_score <- 10
    }
    score_breakdown$rrid <- rrid_score
    availability_score <- availability_score + rrid_score

    # DOI: 10 points
    doi_score <- 0
    if (!is.null(resource_data$doi) && !is.na(resource_data$doi) &&
        resource_data$doi != "" && resource_data$doi != "NULL") {
      doi_score <- 10
    }
    score_breakdown$doi <- doi_score
    availability_score <- availability_score + doi_score
  }

  total_score <- total_score + availability_score

  # Critical info (30 points distributed evenly)
  critical_info_score <- 0

  if (!is.na(tool_type)) {
    if (tool_type == "animal model") {
      # 5 fields: backgroundStrain, backgroundSubstrain, animalModelManifestation, alleleType, affectedGeneSymbol
      fields <- c("backgroundStrain", "backgroundSubstrain", "animalModelManifestation", "alleleType", "affectedGeneSymbol")
    } else if (tool_type == "cell line") {
      # 7 fields: sex, race, age, category, cellLineManifestation, tissue, cellLineGeneticDisorder
      fields <- c("sex", "race", "age", "category", "cellLineManifestation", "tissue", "cellLineGeneticDisorder")
    } else if (tool_type == "antibody") {
      # 2 fields: targetAntigen, basicInfo.reactiveSpecies (may need to check reactiveSpecies)
      fields <- c("targetAntigen", "reactiveSpecies")
    } else if (tool_type == "genetic reagent") {
      # 5 fields: EntrezId, growthTemp, growthStrain, hazardous, bacterialResistance
      fields <- c("EntrezId", "growthTemp", "growthStrain", "hazardous", "bacterialResistance")
    } else if (tool_type == "biobank") {
      # No critical info fields specified for biobank in criteria
      fields <- c()
    } else {
      fields <- c()
    }

    # Count how many critical info fields are filled (evenly distributed to 30 points)
    if (length(fields) > 0) {
      filled_count <- sum(sapply(fields, function(field) {
        !is.null(resource_data[[field]]) && !is.na(resource_data[[field]]) &&
          resource_data[[field]] != "" && resource_data[[field]] != "NULL"
      }))
      critical_info_score <- (filled_count / length(fields)) * 30
    }
  }

  score_breakdown$critical_info <- round(critical_info_score, 1)
  total_score <- total_score + critical_info_score

  # Other info (20 points distributed evenly)
  other_info_score <- 0

  if (!is.na(tool_type)) {
    if (tool_type == "animal model") {
      # 5 fields: synonyms, strainNomenclature, mutationTypes, proteinVariation, sequenceVariation
      fields <- c("synonyms", "strainNomenclature", "mutationTypes", "proteinVariation", "sequenceVariation")
    } else if (tool_type == "cell line") {
      # 2 fields: synonyms, populationDoublingTime
      fields <- c("synonyms", "populationDoublingTime")
    } else if (tool_type == "antibody") {
      # 3 fields: synonyms, conjugated, clonality
      fields <- c("synonyms", "conjugated", "clonality")
    } else if (tool_type == "genetic reagent") {
      # 18 fields
      fields <- c("gRNAshRNAsequence", "insertSize", "nTerminalTag", "cTerminalTag", "cloningMethod",
                  "5primeCloningSite", "5primeSiteDestroyed", "3primeCloningSite", "3primeSiteDestroyed",
                  "promoter", "5primer", "3primer", "vectorBackbone", "vectorType", "backboneSize",
                  "totalSize", "copyNumber", "selectableMarker")
    } else if (tool_type == "biobank") {
      # No other info fields specified for biobank in criteria
      fields <- c()
    } else {
      fields <- c()
    }

    # Count how many other info fields are filled (evenly distributed to 20 points)
    if (length(fields) > 0) {
      filled_count <- sum(sapply(fields, function(field) {
        !is.null(resource_data[[field]]) && !is.na(resource_data[[field]]) &&
          resource_data[[field]] != "" && resource_data[[field]] != "NULL"
      }))
      other_info_score <- (filled_count / length(fields)) * 20
    }
  }

  score_breakdown$other_info <- round(other_info_score, 1)
  total_score <- total_score + other_info_score

  # Observations (10 points max)
  # With DOI: 3 points each, No DOI: 1 point each
  observation_score <- 0
  if (!is.null(observations_data) && nrow(observations_data) > 0) {
    for (i in 1:nrow(observations_data)) {
      obs <- observations_data[i, ]
      # Check if observation has a DOI
      has_doi <- !is.null(obs$doi) && !is.na(obs$doi) && obs$doi != "" && obs$doi != "NULL"

      if (has_doi) {
        observation_score <- observation_score + 3
      } else {
        observation_score <- observation_score + 1
      }

      # Cap at 10 points
      if (observation_score >= 10) {
        observation_score <- 10
        break
      }
    }
  }
  score_breakdown$observations <- observation_score
  total_score <- total_score + observation_score

  return(list(
    total_score = round(total_score, 1),
    breakdown = score_breakdown
  ))
}

# Main scoring function
score_all_tools <- function() {
  
  # Read the comprehensive materialized view
  cat("Reading Resource data from Synapse...\n")
  resource_query <- synTableQuery(
    "SELECT * FROM syn51730943"
  )
  resource_df <- as.data.frame(resource_query)
  
  # Read observations data
  cat("Reading Observation data from Synapse...\n")
  obs_query <- synTableQuery(
    "SELECT * FROM syn26486836"
  )
  obs_df <- as.data.frame(obs_query)
  
  # Initialize results dataframe
  results <- data.frame()
  
  # Calculate scores for each resource
  cat("Calculating scores...\n")
  for (i in 1:nrow(resource_df)) {
    resource <- resource_df[i, ]
    
    # Get observations for this resource/donor
    resource_obs <- obs_df %>%
      filter(donorId == resource$donorId)
    
    # Calculate score
    score_result <- calculate_tool_score(resource, resource_obs)

    # Create result row
    result_row <- data.frame(
      resourceId = resource$resourceId,
      resourceName = resource$resourceName,
      resourceType = resource$resourceType,
      rrid = resource$rrid,
      total_score = score_result$total_score,
      biobank_url_score = ifelse(is.null(score_result$breakdown$biobank_url), NA, score_result$breakdown$biobank_url),
      vendor_developer_score = ifelse(is.null(score_result$breakdown$vendor_developer), NA, score_result$breakdown$vendor_developer),
      rrid_score = ifelse(is.null(score_result$breakdown$rrid), NA, score_result$breakdown$rrid),
      doi_score = ifelse(is.null(score_result$breakdown$doi), NA, score_result$breakdown$doi),
      critical_info_score = score_result$breakdown$critical_info,
      other_info_score = score_result$breakdown$other_info,
      observation_score = score_result$breakdown$observations,
      stringsAsFactors = FALSE
    )
    
    results <- rbind(results, result_row)
  }
  
  # Add completeness category
  results <- results %>%
    mutate(
      completeness_category = case_when(
        total_score >= 80 ~ "Excellent",
        total_score >= 60 ~ "Good",
        total_score >= 40 ~ "Fair",
        total_score >= 20 ~ "Poor",
        TRUE ~ "Minimal"
      )
    )
  
  return(results)
}

# Generate summary statistics by tool type
summarize_scores <- function(scores_df) {
  summary_stats <- scores_df %>%
    group_by(resourceType) %>%
    summarise(
      count = n(),
      mean_score = mean(total_score, na.rm = TRUE),
      median_score = median(total_score, na.rm = TRUE),
      min_score = min(total_score, na.rm = TRUE),
      max_score = max(total_score, na.rm = TRUE),
      sd_score = sd(total_score, na.rm = TRUE),
      excellent = sum(completeness_category == "Excellent"),
      good = sum(completeness_category == "Good"),
      fair = sum(completeness_category == "Fair"),
      poor = sum(completeness_category == "Poor"),
      minimal = sum(completeness_category == "Minimal")
    ) %>%
    arrange(desc(mean_score))
  
  return(summary_stats)
}

# Run the analysis
cat("Starting tool completeness scoring...\n")
all_scores <- score_all_tools()

# Generate summary
summary_by_type <- summarize_scores(all_scores)

# Display results
cat("\n=== Summary by Tool Type ===\n")
print(summary_by_type)

cat("\n=== Top 10 Most Complete Tools ===\n")
print(all_scores %>% 
        arrange(desc(total_score)) %>% 
        select(resourceName, resourceType, rrid, total_score, completeness_category) %>%
        head(10))

cat("\n=== Tools Needing Improvement (Score < 40) ===\n")
incomplete_tools <- all_scores %>%
  filter(total_score < 40) %>%
  arrange(total_score) %>%
  select(resourceName, resourceType, total_score, completeness_category)

print(head(incomplete_tools, 20))

# Save results to CSV
write.csv(all_scores, "tool_completeness_scores.csv", row.names = FALSE)
write.csv(summary_by_type, "tool_completeness_summary.csv", row.names = FALSE)

cat("\n✓ Results saved to:\n")
cat("  - tool_completeness_scores.csv\n")
cat("  - tool_completeness_summary.csv\n")

# Store results as a Synapse table
cat("\nStoring results as Synapse table...\n")

# Define table schema
table_schema <- TableSchema(
  name = "ToolCompletenessScores",
  parent = "syn26338068",
  columns = list(
    Column(name = "resourceId", columnType = "STRING", maximumSize = 50),
    Column(name = "resourceName", columnType = "STRING", maximumSize = 255),
    Column(name = "resourceType", columnType = "STRING", maximumSize = 50),
    Column(name = "rrid", columnType = "STRING", maximumSize = 100),
    Column(name = "total_score", columnType = "DOUBLE"),
    Column(name = "biobank_url_score", columnType = "DOUBLE"),
    Column(name = "vendor_developer_score", columnType = "DOUBLE"),
    Column(name = "rrid_score", columnType = "DOUBLE"),
    Column(name = "doi_score", columnType = "DOUBLE"),
    Column(name = "critical_info_score", columnType = "DOUBLE"),
    Column(name = "other_info_score", columnType = "DOUBLE"),
    Column(name = "observation_score", columnType = "DOUBLE"),
    Column(name = "completeness_category", columnType = "STRING", maximumSize = 50)
  )
)

# Create and store the table
table_object <- Table(table_schema, all_scores)
table_result <- synStore(table_object)

cat("\n✓ Completeness scores stored as Synapse table:", table_result$tableId, "\n")
cat("  View at: https://www.synapse.org/Synapse:", table_result$tableId, "\n")

# Also store summary statistics as a separate table
cat("\nStoring summary statistics as Synapse table...\n")

summary_schema <- TableSchema(
  name = "ToolCompletenessSummary",
  parent = "syn26338068",
  columns = list(
    Column(name = "resourceType", columnType = "STRING", maximumSize = 50),
    Column(name = "count", columnType = "INTEGER"),
    Column(name = "mean_score", columnType = "DOUBLE"),
    Column(name = "median_score", columnType = "DOUBLE"),
    Column(name = "min_score", columnType = "DOUBLE"),
    Column(name = "max_score", columnType = "DOUBLE"),
    Column(name = "sd_score", columnType = "DOUBLE"),
    Column(name = "excellent", columnType = "INTEGER"),
    Column(name = "good", columnType = "INTEGER"),
    Column(name = "fair", columnType = "INTEGER"),
    Column(name = "poor", columnType = "INTEGER"),
    Column(name = "minimal", columnType = "INTEGER")
  )
)

# Create and store the summary table
summary_table_object <- Table(summary_schema, summary_by_type)
summary_table_result <- synStore(summary_table_object)

cat("✓ Summary statistics stored as Synapse table:", summary_table_result$tableId, "\n")
cat("  View at: https://www.synapse.org/Synapse:", summary_table_result$tableId, "\n")
