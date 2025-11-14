library(synapser)
library(dplyr)
library(tidyr)

# Login to Synapse
synLogin()

# Read base Resource table
cat("Reading base Resource data from Synapse...\n")
resource_query <- synTableQuery(
  "SELECT * FROM syn26450069"
)
resource_df <- as.data.frame(resource_query)

# Read type-specific tables
cat("Reading Animal Model data...\n")
animal_model_query <- synTableQuery("SELECT * FROM syn26486808")
animal_model_df <- as.data.frame(animal_model_query)

cat("Reading Antibody data...\n")
antibody_query <- synTableQuery("SELECT * FROM syn26486811")
antibody_df <- as.data.frame(antibody_query)

cat("Reading Biobank data...\n")
biobank_query <- synTableQuery("SELECT * FROM syn26486821")
biobank_df <- as.data.frame(biobank_query)

cat("Reading Cell Line data...\n")
cell_line_query <- synTableQuery("SELECT * FROM syn26486823")
cell_line_df <- as.data.frame(cell_line_query)

cat("Reading Genetic Reagent data...\n")
genetic_reagent_query <- synTableQuery("SELECT * FROM syn26486832")
genetic_reagent_df <- as.data.frame(genetic_reagent_query)

# Join base resource data with type-specific data
cat("Joining resource data with type-specific tables...\n")

# Create full dataset by joining based on type-specific IDs
resource_df <- resource_df %>%
  left_join(
    animal_model_df %>% filter(!is.na(animalModelId)),
    by = "animalModelId",
    suffix = c("", ".animal")
  ) %>%
  left_join(
    antibody_df %>% filter(!is.na(antibodyId)),
    by = "antibodyId",
    suffix = c("", ".antibody")
  ) %>%
  left_join(
    biobank_df %>% filter(!is.na(biobankId)),
    by = "biobankId",
    suffix = c("", ".biobank")
  ) %>%
  left_join(
    cell_line_df %>% filter(!is.na(cellLineId)),
    by = "cellLineId",
    suffix = c("", ".cellline")
  ) %>%
  left_join(
    genetic_reagent_df %>% filter(!is.na(geneticReagentId)),
    by = "geneticReagentId",
    suffix = c("", ".genetic")
  )

cat(sprintf("Loaded %d resources\n", nrow(resource_df)))
cat(sprintf("Resource types: %s\n", paste(unique(resource_df$resourceType), collapse=", ")))

# Function to calculate field completion rate
calculate_completion_rate <- function(df, field) {
  total <- nrow(df)
  if (total == 0) return(0)

  filled <- sum(!is.na(df[[field]]) &
                df[[field]] != "" &
                df[[field]] != "NULL",
                na.rm = TRUE)
  return(round((filled / total) * 100, 1))
}

# Function to analyze fields for a specific resource type
analyze_resource_type <- function(df, resource_type) {
  cat("\n================================================\n")
  cat(sprintf("ANALYZING: %s\n", toupper(resource_type)))
  cat("================================================\n")

  # Filter for this resource type
  type_df <- df %>% filter(resourceType == resource_type)

  if (nrow(type_df) == 0) {
    cat("No resources found for this type.\n")
    return(NULL)
  }

  cat(sprintf("Total resources: %d\n\n", nrow(type_df)))

  # Get all column names
  all_fields <- names(type_df)

  # Exclude standard metadata fields and date/POSIXct columns
  exclude_fields <- c("resourceId", "resourceName", "resourceType", "rrid",
                     "synId", "ROW_ID", "ROW_VERSION", "ROW_ETAG",
                     "donorId", "dateCreated", "createdBy")

  # Also exclude POSIXct/date columns to avoid parsing errors
  date_columns <- sapply(all_fields, function(f) {
    inherits(type_df[[f]], c("POSIXct", "POSIXt", "Date"))
  })
  exclude_fields <- c(exclude_fields, all_fields[date_columns])

  # Filter to relevant fields
  relevant_fields <- setdiff(all_fields, exclude_fields)

  # Calculate completion rates
  completion_rates <- data.frame(
    field = relevant_fields,
    completion_rate = sapply(relevant_fields, function(f) {
      calculate_completion_rate(type_df, f)
    }),
    stringsAsFactors = FALSE
  ) %>%
    arrange(desc(completion_rate))

  # Categorize fields
  high_completion <- completion_rates %>% filter(completion_rate >= 50)
  medium_completion <- completion_rates %>% filter(completion_rate >= 20 & completion_rate < 50)
  low_completion <- completion_rates %>% filter(completion_rate < 20)

  # Print results
  cat("HIGH COMPLETION (>= 50%) - CRITICAL INFO:\n")
  cat("------------------------------------------\n")
  if (nrow(high_completion) > 0) {
    for (i in 1:nrow(high_completion)) {
      cat(sprintf("  %s: %.1f%%\n",
                  high_completion$field[i],
                  high_completion$completion_rate[i]))
    }
  } else {
    cat("  (none)\n")
  }

  cat("\nMEDIUM COMPLETION (20-49%):\n")
  cat("---------------------------\n")
  if (nrow(medium_completion) > 0) {
    for (i in 1:nrow(medium_completion)) {
      cat(sprintf("  %s: %.1f%%\n",
                  medium_completion$field[i],
                  medium_completion$completion_rate[i]))
    }
  } else {
    cat("  (none)\n")
  }

  cat("\nLOW COMPLETION (< 20%) - OTHER INFO:\n")
  cat("------------------------------------\n")
  if (nrow(low_completion) > 0) {
    for (i in 1:nrow(low_completion)) {
      cat(sprintf("  %s: %.1f%%\n",
                  low_completion$field[i],
                  low_completion$completion_rate[i]))
    }
  } else {
    cat("  (none)\n")
  }

  return(list(
    resource_type = resource_type,
    total_count = nrow(type_df),
    high_completion = high_completion,
    medium_completion = medium_completion,
    low_completion = low_completion
  ))
}

# Analyze each resource type
resource_types <- unique(resource_df$resourceType)
resource_types <- resource_types[!is.na(resource_types)]

results <- list()
for (rt in resource_types) {
  results[[rt]] <- analyze_resource_type(resource_df, rt)
}

# Save results summary
cat("\n\n================================================\n")
cat("SUMMARY FOR CRITERIA.MD UPDATE\n")
cat("================================================\n\n")

for (rt in names(results)) {
  if (!is.null(results[[rt]])) {
    cat(sprintf("**%s (%d resources)**\n", rt, results[[rt]]$total_count))

    cat("Critical info (high completion): ")
    if (nrow(results[[rt]]$high_completion) > 0) {
      cat(paste(results[[rt]]$high_completion$field, collapse=", "))
    } else {
      cat("(none)")
    }
    cat("\n")

    cat("Other info (low completion): ")
    if (nrow(results[[rt]]$low_completion) > 0) {
      cat(paste(results[[rt]]$low_completion$field, collapse=", "))
    } else {
      cat("(none)")
    }
    cat("\n\n")
  }
}

cat("\nAnalysis complete!\n")
